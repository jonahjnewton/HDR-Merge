cmake_minimum_required(VERSION 2.6)

include(RezBuild)

FILE(GLOB_RECURSE blender_files blender/*)
rez_install_files(
	${blender_files}
	DESTINATION .
	LOCAL_SYMLINK
)

FILE(GLOB_RECURSE icon_files icons/*)
rez_install_files(
	${icon_files}
	DESTINATION .
	LOCAL_SYMLINK
)

FILE(GLOB_RECURSE bin_files bin/*)
rez_install_files(
	${bin_files}
	DESTINATION .
	LOCAL_SYMLINK
	EXECUTABLE
)

# FILE(GLOB_RECURSE build_files build/*)
# rez_install_files(
# 	${build_files}
# 	DESTINATION .
# 	LOCAL_SYMLINK
# )

FILE(GLOB_RECURSE py_files python/*.py)
rez_install_python(
	py_files
	FILES
	${py_files}
	DESTINATION .
	LOCAL_SYMLINK
)