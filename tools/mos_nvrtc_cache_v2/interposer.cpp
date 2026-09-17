// Experimental single-scene PTX + lowered-name cache. Never enabled by normal launch.
#include "mos_nvrtc_cache/key.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <map>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

using Program = void*;
namespace {
using Bytes = std::vector<std::uint8_t>;
constexpr std::size_t MAX = 64 * 1024 * 1024;
struct State {
    Bytes identity;
    std::vector<std::string> expressions;
    std::map<std::string, std::string> names;
    std::string ptx, key;
    bool replay = false;
};
std::mutex mutex;
std::map<Program, std::shared_ptr<State>> states;
std::string env(const char* name) { const char* p = std::getenv(name); return p ? p : ""; }
void log(const char* event, const std::string& detail) {
    const auto ns = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::system_clock::now().time_since_epoch()).count();
    std::fprintf(stderr, "MOS_V2 event=%s epoch_ns=%lld %s\n", event, static_cast<long long>(ns), detail.c_str());
}
void* library() {
    static void* handle = [] {
        const auto path = env("MOS_V2_LIBRARY");
        return path.empty() ? nullptr : dlopen(path.c_str(), RTLD_NOW | RTLD_LOCAL);
    }();
    return handle;
}
template<class T> T original(const char* name) {
    if (!library()) throw std::runtime_error("original library unavailable");
    const auto p = dlsym(library(), name);
    if (!p) throw std::runtime_error(name);
    return reinterpret_cast<T>(p);
}
std::shared_ptr<State> state(Program p) {
    std::lock_guard<std::mutex> lock(mutex);
    const auto it = states.find(p);
    return it == states.end() ? nullptr : it->second;
}
void append(Bytes& b, const std::string& s) {
    const std::uint64_t n = s.size();
    for (int i = 0; i < 8; ++i) b.push_back(static_cast<std::uint8_t>(n >> (8*i)));
    b.insert(b.end(), s.begin(), s.end());
}
std::string take(const Bytes& b, std::size_t& pos) {
    if (b.size()-pos < 8) throw std::runtime_error("truncated length");
    std::uint64_t n = 0;
    for (int i=0;i<8;++i) n |= std::uint64_t(b[pos++]) << (8*i);
    if (n > MAX || n > b.size()-pos) throw std::runtime_error("invalid length");
    std::string s(b.begin()+pos, b.begin()+pos+n); pos += n; return s;
}
bool enabled() { return !env("MOS_V2_SCOPE").empty() && !env("MOS_V2_DIR").empty() &&
    (env("MOS_V2_MODE")=="seed" || env("MOS_V2_MODE")=="replay"); }
void track(Program p, const char* src, const char* name, int count,
           const char* const* headers, const char* const* includes, std::uintptr_t extra, bool privateApi) {
    if (!enabled() || !p || !src || count < 0 || count > 4096 || (count && (!headers || !includes))) return;
    // Private CPEx is intentionally restricted to an explicitly acknowledged single-scene experiment.
    if (privateApi && env("MOS_V2_PRIVATE_EXPERIMENT") != "1") {
        log("bypass", "reason=private-inputs-not-approved"); return;
    }
    auto s = std::make_shared<State>();
    append(s->identity,"mos-ptx-names-v2");
    append(s->identity, env("MOS_V2_SCOPE"));
    static const std::string digest = mos_nvrtc_cache::sha256_file(env("MOS_V2_LIBRARY")).value_or("");
    if (digest.empty()) return;
    append(s->identity,digest); append(s->identity,src); append(s->identity,name ? name : "");
    append(s->identity,std::to_string(count));
    for(int i=0;i<count;++i) {
        if(!headers[i] || !includes[i]) return;
        append(s->identity,includes[i]); append(s->identity,headers[i]);
    }
    append(s->identity, privateApi ? "private-experimental" : "public");
    append(s->identity, std::to_string(extra));
    std::lock_guard<std::mutex> lock(mutex); states[p]=s;
    log("tracked", "private="+std::to_string(privateApi));
}
bool read(State& s) {
    try {
        const auto path=std::filesystem::path(env("MOS_V2_DIR"))/(s.key+".bin");
        if(!std::filesystem::is_regular_file(path) || std::filesystem::file_size(path)>MAX) return false;
        std::ifstream in(path,std::ios::binary);
        Bytes b((std::istreambuf_iterator<char>(in)),{});
        if(b.size()<64) return false;
        const std::string digest(b.begin(),b.begin()+64);
        Bytes payload(b.begin()+64,b.end());
        if(mos_nvrtc_cache::sha256_hex(payload)!=digest) return false;
        std::size_t pos=0;
        if(take(payload,pos)!="mos-ptx-names-v2" || take(payload,pos)!=s.key) return false;
        auto ptx=take(payload,pos);
        if(ptx.empty() || ptx.back()!=0) return false;
        std::map<std::string,std::string> names;
        for(const auto& expr:s.expressions) {
            if(take(payload,pos)!=expr) return false;
            auto lowered=take(payload,pos);
            if(lowered.empty() || lowered.find('\0')!=std::string::npos || ptx.find(lowered)==std::string::npos) return false;
            names.emplace(expr,std::move(lowered));
        }
        if(pos!=payload.size()) return false;
        s.ptx=std::move(ptx); s.names=std::move(names); return true;
    } catch(const std::exception& e) { log("cache_rejected",e.what()); return false; }
}
void persist(const State& s) {
    Bytes b;
    append(b,"mos-ptx-names-v2"); append(b,s.key); append(b,s.ptx);
    for(const auto& expr:s.expressions) { append(b,expr); append(b,s.names.at(expr)); }
    const auto digest=mos_nvrtc_cache::sha256_hex(b);
    const auto dir=std::filesystem::path(env("MOS_V2_DIR"));
    std::filesystem::create_directories(dir);
    std::string pattern=(dir/(s.key+".tmp.XXXXXX")).string();
    std::vector<char> temp(pattern.begin(),pattern.end()); temp.push_back(0);
    int fd=mkstemp(temp.data()); if(fd<0) return;
    Bytes all(digest.begin(),digest.end()); all.insert(all.end(),b.begin(),b.end());
    std::size_t done=0;
    while(done<all.size()) { const auto n=::write(fd,all.data()+done,all.size()-done); if(n<=0) break; done+=n; }
    const bool synced=done==all.size() && fsync(fd)==0;
    close(fd);
    if(synced && rename(temp.data(),(dir/(s.key+".bin")).c_str())==0)
        log("stored","key="+s.key+" names="+std::to_string(s.names.size())+" ptx_bytes="+std::to_string(s.ptx.size()));
    else unlink(temp.data());
}
} // namespace

extern "C" int nvrtcCreateProgram(Program* p,const char* src,const char* name,int n,const char* const* h,const char* const* inc) {
    try {
        const int r=original<int(*)(Program*,const char*,const char*,int,const char* const*,const char* const*)>("nvrtcCreateProgram")(p,src,name,n,h,inc);
        if(r==0 && p) { try {track(*p,src,name,n,h,inc,0,false);} catch(const std::exception& e){log("track_error",e.what());} }
        return r;
    } catch(const std::exception& e){log("error",e.what());return 11;}
}
extern "C" int __nvrtcCPEx(Program* p,const char* src,const char* name,int n,const char* const* h,const char* const* inc,std::uintptr_t a,std::uintptr_t b,std::uintptr_t c) {
    try {
        const int r=original<int(*)(Program*,const char*,const char*,int,const char* const*,const char* const*,std::uintptr_t,std::uintptr_t,std::uintptr_t)>("__nvrtcCPEx")(p,src,name,n,h,inc,a,b,c);
        if(r==0 && p) { try {track(*p,src,name,n,h,inc,a,true);} catch(const std::exception& e){log("track_error",e.what());} }
        return r;
    } catch(const std::exception& e){log("error",e.what());return 11;}
}
extern "C" int nvrtcAddNameExpression(Program p,const char* expr) {
    try {
        auto s=state(p);
        if(s && s->replay) return 8;
        const int r=original<int(*)(Program,const char*)>("nvrtcAddNameExpression")(p,expr);
        if(r==0 && s && expr) s->expressions.emplace_back(expr);
        return r;
    } catch(const std::exception& e){log("error",e.what());return 11;}
}
extern "C" int nvrtcCompileProgram(Program p,int n,const char* const* opts) {
    try {
        auto s=state(p);
        if(s) { s->replay=false; s->ptx.clear(); s->names.clear(); }
        if(s && n>=0 && (!n || opts) && !s->expressions.empty()) {
            Bytes key=s->identity; append(key,std::to_string(n));
            for(int i=0;i<n;++i) append(key,opts[i] ? opts[i] : "");
            append(key,std::to_string(s->expressions.size()));
            for(const auto& expr:s->expressions) append(key,expr);
            s->key=mos_nvrtc_cache::sha256_hex(key);
            if(env("MOS_V2_MODE")=="replay" && read(*s)) {
                s->replay=true; log("hit","key="+s->key+" names="+std::to_string(s->names.size())); return 0;
            }
        }
        auto started=std::chrono::steady_clock::now();
        log("compile_begin",s ? "key="+s->key : "untracked=1");
        const int r=original<int(*)(Program,int,const char* const*)>("nvrtcCompileProgram")(p,n,opts);
        const auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(std::chrono::steady_clock::now()-started).count();
        log("compile","result="+std::to_string(r)+" ms="+std::to_string(ms));
        if(r==0 && s && !s->key.empty()) {
            try {
                for(const auto& expr:s->expressions) {
                    const char* lowered=nullptr;
                    if(original<int(*)(Program,const char*,const char**)>("nvrtcGetLoweredName")(p,expr.c_str(),&lowered)!=0 || !lowered)
                        throw std::runtime_error("missing lowered name");
                    s->names[expr]=lowered;
                }
                std::size_t size=0;
                if(original<int(*)(Program,std::size_t*)>("nvrtcGetPTXSize")(p,&size)!=0 || !size || size>MAX)
                    throw std::runtime_error("invalid PTX size");
                s->ptx.resize(size);
                if(original<int(*)(Program,char*)>("nvrtcGetPTX")(p,s->ptx.data())!=0)
                    throw std::runtime_error("get PTX failed");
                persist(*s);
            } catch(const std::exception& e){log("store_skipped",e.what());}
        }
        return r;
    } catch(const std::exception& e){log("error",e.what());return 11;}
}
extern "C" int nvrtcGetLoweredName(Program p,const char* expr,const char** out) {
    try {
        auto s=state(p);
        if(s && s->replay) {
            if(!out || !expr) return 3;
            const auto it=s->names.find(expr);
            if(it==s->names.end()) return 10;
            *out=it->second.c_str(); log("name_hit",expr); return 0;
        }
        return original<int(*)(Program,const char*,const char**)>("nvrtcGetLoweredName")(p,expr,out);
    } catch(const std::exception& e){log("error",e.what());return 11;}
}
extern "C" int nvrtcGetPTXSize(Program p,std::size_t* out) {
    try { auto s=state(p); if(s && s->replay){if(!out)return 3; *out=s->ptx.size();return 0;}
        return original<int(*)(Program,std::size_t*)>("nvrtcGetPTXSize")(p,out);
    }catch(const std::exception& e){log("error",e.what());return 11;}
}
extern "C" int nvrtcGetPTX(Program p,char* out) {
    try { auto s=state(p); if(s && s->replay){if(!out)return 3; std::memcpy(out,s->ptx.data(),s->ptx.size());return 0;}
        return original<int(*)(Program,char*)>("nvrtcGetPTX")(p,out);
    }catch(const std::exception& e){log("error",e.what());return 11;}
}
extern "C" int nvrtcDestroyProgram(Program* p) {
    try { const auto handle=p ? *p : nullptr;
        const int r=original<int(*)(Program*)>("nvrtcDestroyProgram")(p);
        if(r==0){std::lock_guard<std::mutex> lock(mutex); states.erase(handle);} return r;
    }catch(const std::exception& e){log("error",e.what());return 11;}
}
