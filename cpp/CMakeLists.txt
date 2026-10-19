cmake_minimum_required(VERSION 3.20)
project(DeskControlPro LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

# ─── ملفات المصدر ───
set(SOURCES
    main.cpp
    resource.rc
)

# ─── ملف تنفيذي بنافذة (بدون Console) ───
add_executable(DeskControl WIN32 ${SOURCES})

# ─── مكتبات Windows ───
target_link_libraries(DeskControl PRIVATE
    gdi32
    gdiplus
    ws2_32
    comctl32
    uxtheme
)

# ─── تعريفات المعالج المسبق ───
target_compile_definitions(DeskControl PRIVATE
    UNICODE
    _UNICODE
    WIN32_LEAN_AND_MEAN
    _WIN32_WINNT=0x0601   # Windows 7 minimum
    WINVER=0x0601
)

# ─── خيارات الترجمة (MSVC) ───
if(MSVC)
    target_compile_options(DeskControl PRIVATE
        /W3          # تحذيرات معقولة
        /MP          # ترجمة متوازية
        /utf-8       # ترميز UTF-8
        /Zc:__cplusplus
    )
    # تضمين وقت التشغيل ستاتيكياً (ملف exe مستقل)
    set_property(TARGET DeskControl PROPERTY
        MSVC_RUNTIME_LIBRARY "MultiThreaded$<$<CONFIG:Debug>:Debug>")
    # تعطيل نافذة الـ Console في Release
    set_target_properties(DeskControl PROPERTIES
        LINK_FLAGS_RELEASE "/SUBSYSTEM:WINDOWS /ENTRY:WinMainCRTStartup")
endif()

# ─── خيارات الترجمة (GCC / MinGW) ───
if(MINGW OR CMAKE_CXX_COMPILER_ID STREQUAL "GNU")
    target_compile_options(DeskControl PRIVATE
        -Wall -Wextra -O2
        -finput-charset=UTF-8
        -fexec-charset=UTF-8
    )
    target_link_options(DeskControl PRIVATE
        -mwindows          # بدون نافذة Console
        -static            # ربط ستاتيكي لـ libgcc/libstdc++
        -static-libgcc
        -static-libstdc++
    )
endif()

# ─── نسخ الأصول عند البناء ───
# add_custom_command(TARGET DeskControl POST_BUILD
#     COMMAND ${CMAKE_COMMAND} -E copy_directory
#         "${CMAKE_SOURCE_DIR}/assets"
#         "$<TARGET_FILE_DIR:DeskControl>/assets"
#     COMMENT "Copying assets..."
# )

message(STATUS "Configuring DeskControl Pro v5.0")
message(STATUS "  Compiler : ${CMAKE_CXX_COMPILER_ID}")
message(STATUS "  Build dir: ${CMAKE_BINARY_DIR}")
