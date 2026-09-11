local ext = get_current_extension_info()

project_ext(ext)

repo_build.prebuild_link {
    { "nycu", ext.target_dir.."/nycu" },
}
