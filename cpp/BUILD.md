# بناء DeskControl Pro (C++)

## المتطلبات

| الأداة | الإصدار الأدنى | التنزيل |
|--------|----------------|---------|
| MinGW-w64 (GCC) | 13+ | https://winlibs.com |
| أو MSVC | 2019+ | Visual Studio |
| CMake | 3.20+ | https://cmake.org |

> **ملاحظة:** مكتبة GDI+ مدمجة مع Windows — لا حاجة لتثبيت إضافي.

---

## البناء بـ MinGW (الأسرع)

```bat
:: من داخل مجلد cpp\
mkdir build && cd build
cmake .. -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
mingw32-make -j4
```
الناتج: `build\DeskControl.exe`

---

## البناء المباشر بـ g++ (بدون CMake)

```bat
g++ main.cpp resource.rc -o DeskControl.exe ^
    -lgdi32 -lgdiplus -lws2_32 -lcomctl32 -luxtheme ^
    -mwindows -static -static-libgcc -static-libstdc++ ^
    -std=c++17 -O2 -DUNICODE -D_UNICODE
```

---

## البناء بـ MSVC (Visual Studio)

```bat
mkdir build && cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

---

## هيكل الملفات

```
cpp/
├── main.cpp        ← الكود الرئيسي (Win32 + GDI+)
├── resource.rc     ← الموارد (إصدار، DPI manifest)
├── CMakeLists.txt  ← ملف البناء
├── BUILD.md        ← هذا الملف
└── assets/
    └── icon.ico    ← (اختياري) أيقونة التطبيق
```

---

## الوظائف المنجزة

- [x] واجهة داكنة كاملة (Win32 + GDI+ Anti-aliased)
- [x] Header مع شعار وبادجات
- [x] بطاقة "جهازك" (Device ID + Password)
- [x] بطاقة "الاتصال البعيد" (Remote ID + PW + زر Connect)
- [x] Footer مع نبضة حية (animated dot)
- [x] Toast إشعارات طافية
- [x] Hit-testing للأزرار + cursor يتغير للـ hand
- [x] Winsock2 لقراءة الـ IP المحلي
- [x] DPI Awareness (PerMonitorV2)
- [x] Double-buffering (لا وميض)
- [ ] منطق الاتصال الكامل (Screen Capture + Input injection)
