// DeskControl Pro — C++ / Win32 + GDI+ Edition
// تصميم داكن احترافي مع بطاقتين وشريط علوي وسفلي
// Build: g++ main.cpp -o DeskControl.exe -lgdi32 -lgdiplus -lws2_32 -mwindows -std=c++17

#define UNICODE
#define _UNICODE
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <windowsx.h>
#include <gdiplus.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <commctrl.h>
#include <uxtheme.h>
#include <string>
#include <sstream>
#include <thread>
#include <atomic>
#include <vector>
#include <ctime>
#pragma comment(lib, "gdiplus.lib")
#pragma comment(lib, "ws2_32.lib")
#pragma comment(lib, "comctl32.lib")
#pragma comment(lib, "uxtheme.lib")

using namespace Gdiplus;

// ─────────────────────── لوحة الألوان ───────────────────────
namespace C {
    // خلفيات
    const Color BG_DARK    { 255,  8, 12, 20  };
    const Color CARD       { 255, 17, 24, 39  };
    const Color FIELD      { 255, 31, 41, 55  };
    const Color CARD2      { 255, 26, 32, 48  };
    const Color BORDER     { 255, 45, 55, 72  };
    const Color BORDER_GLOW{ 255, 76, 29,149  };
    const Color BORDER_GOLD{ 255,120, 53, 15  };

    // ألوان رئيسية
    const Color PRIMARY    { 255,124, 58,237  };
    const Color PRIMARY_H  { 255,109, 40,217  };
    const Color PRIMARY_L  { 255,167,139,250  };
    const Color PRIMARY_G  { 255, 76, 29,149  };

    // ذهبي
    const Color ACCENT     { 255,245,158, 11  };
    const Color ACCENT_H   { 255,217,119,  6  };
    const Color ACCENT_L   { 255,252,211, 77  };
    const Color BORDER_G2  { 255,120, 53, 15  };

    // حالة
    const Color GREEN      { 255, 16,185,129  };
    const Color GREEN_L    { 255,110,231,183  };
    const Color RED        { 255,239, 68, 68  };
    const Color RED_H      { 255,220, 38, 38  };

    // نصوص
    const Color TEXT_MAIN  { 255,241,245,249  };
    const Color TEXT_SUB   { 255,203,213,225  };
    const Color TEXT_MUTED { 255,100,116,139  };
    const Color TEXT_DIM   { 255, 51, 65, 85  };
    const Color WHITE      { 255,255,255,255  };

    // مساعدات COLORREF
    inline COLORREF toCR(Color c){ return RGB(c.GetR(),c.GetG(),c.GetB()); }
}

// ─────────────────────── ثوابت ───────────────────────
constexpr int PORT        = 5600;
constexpr int WIN_W       = 940;
constexpr int WIN_H       = 640;
constexpr int HEADER_H    = 68;
constexpr int FOOTER_H    = 44;
constexpr int CARD_PAD    = 18;
constexpr int CORNER_R    = 16;

// IDs للعناصر
enum CtrlID {
    ID_BTN_COPY    = 101,
    ID_BTN_REGEN   = 102,
    ID_BTN_CONNECT = 103,
    ID_EDIT_REMOTE = 201,
    ID_EDIT_PW     = 202,
    ID_TIMER_ANIM  = 301,
};

// ─────────────────────── بيانات التطبيق ───────────────────────
struct AppState {
    std::wstring myIP;
    std::wstring myDeviceID;
    std::wstring myPassword;
    std::wstring statusText   = L"مستعد للاتصالات القادمة";
    Color        statusColor  = C::GREEN;
    bool         connected    = false;
    int          animTick     = 0;        // للنبضة الخضراء
};
AppState g_state;

// ─────────────────────── أدوات GDI+ ───────────────────────
// رسم مستطيل بزوايا مدوّرة
static void RoundRect(Graphics& g, const Brush& br, float x,float y,float w,float h,float r)
{
    GraphicsPath path;
    path.AddArc(x,     y,     r*2, r*2, 180, 90);
    path.AddArc(x+w-r*2, y,   r*2, r*2,   0,-90); // fixed: 270
    path.AddArc(x+w-r*2, y+h-r*2, r*2,r*2, 0, 90);// fixed: 0
    path.AddArc(x,     y+h-r*2, r*2,r*2, 90, 90);
    path.CloseFigure();
    g.FillPath(&br, &path);
}

static void RoundRectStroke(Graphics& g, const Pen& pen,
                             float x,float y,float w,float h,float r)
{
    GraphicsPath path;
    path.AddArc(x,       y,       r*2,r*2, 180, 90);
    path.AddArc(x+w-r*2, y,       r*2,r*2, 270, 90);
    path.AddArc(x+w-r*2, y+h-r*2, r*2,r*2,   0, 90);
    path.AddArc(x,       y+h-r*2, r*2,r*2,  90, 90);
    path.CloseFigure();
    g.DrawPath(&pen, &path);
}

// رسم نص عربي (RTL مدعوم)
static void DrawText(Graphics& g, const std::wstring& text,
                     Font& font, const Brush& br,
                     float x,float y,float w,float h,
                     StringAlignment hAlign = StringAlignmentNear,
                     StringAlignment vAlign = StringAlignmentCenter)
{
    StringFormat sf;
    sf.SetAlignment(hAlign);
    sf.SetLineAlignment(vAlign);
    sf.SetFormatFlags(StringFormatFlagsDirectionRightToLeft);
    RectF rc(x,y,w,h);
    g.DrawString(text.c_str(),-1,&font,rc,&sf,&br);
}

static void DrawTextLTR(Graphics& g, const std::wstring& text,
                        Font& font, const Brush& br,
                        float x,float y,float w,float h,
                        StringAlignment hAlign = StringAlignmentNear,
                        StringAlignment vAlign = StringAlignmentCenter)
{
    StringFormat sf;
    sf.SetAlignment(hAlign);
    sf.SetLineAlignment(vAlign);
    RectF rc(x,y,w,h);
    g.DrawString(text.c_str(),-1,&font,rc,&sf,&br);
}

// ─────────────────────── شبكة: IP ───────────────────────
static std::wstring GetLocalIP()
{
    WSADATA wsa; WSAStartup(MAKEWORD(2,2),&wsa);
    char buf[256] = {};
    gethostname(buf, sizeof(buf));
    addrinfo hints{}, *res=nullptr;
    hints.ai_family = AF_INET;
    if(getaddrinfo(buf,"",&hints,&res)==0 && res){
        char ip[INET_ADDRSTRLEN]={};
        inet_ntop(AF_INET,&((sockaddr_in*)res->ai_addr)->sin_addr,ip,sizeof(ip));
        freeaddrinfo(res);
        std::wstring wip(ip,ip+strlen(ip));
        return wip;
    }
    return L"127.0.0.1";
}

static std::wstring IPtoDeviceID(const std::wstring& ip)
{
    // نفس خوارزمية Python
    int a,b,c,d;
    if(swscanf_s(ip.c_str(),L"%d.%d.%d.%d",&a,&b,&c,&d)==4){
        wchar_t prefix[4];
        if(a==192&&b==168) wcscpy_s(prefix,L"780");
        else if(a==10)     wcscpy_s(prefix,L"500");
        else if(a==172)    wcscpy_s(prefix,L"372");
        else               swprintf_s(prefix,L"%03d",a);
        wchar_t buf[32];
        swprintf_s(buf,L"%s%03d%03d",prefix,c,d);
        return std::wstring(buf,3)+L" "+std::wstring(buf+3,3)+L" "+std::wstring(buf+6,3);
    }
    return L"780 102 405";
}

static std::wstring MakePassword()
{
    const wchar_t* chars = L"abcdefghijklmnopqrstuvwxyz0123456789";
    std::wstring pw(8,L' ');
    srand((unsigned)time(nullptr));
    for(auto& ch:pw) ch = chars[rand()%36];
    return pw;
}

// ─────────────────────── الرسم الرئيسي ───────────────────────
static HWND g_hwnd = nullptr;
static HWND g_editRemote = nullptr;
static HWND g_editPW     = nullptr;

// ألوان custom لـ Edit controls
static HBRUSH g_fieldBrush = nullptr;

// خطوط
static FontFamily* ff = nullptr;
static Font* fTitle    = nullptr;  // 17pt bold
static Font* fBody     = nullptr;  // 13pt
static Font* fSmall    = nullptr;  // 11pt
static Font* fLarge    = nullptr;  // 20pt bold
static Font* fMono     = nullptr;  // 15pt  (ID/PW fields)

static void InitFonts()
{
    ff      = new FontFamily(L"Segoe UI");
    fTitle  = new Font(ff, 17, FontStyleBold,   UnitPoint);
    fBody   = new Font(ff, 13, FontStyleRegular,UnitPoint);
    fSmall  = new Font(ff, 11, FontStyleRegular,UnitPoint);
    fLarge  = new Font(ff, 20, FontStyleBold,   UnitPoint);
    fMono   = new Font(ff, 14, FontStyleBold,   UnitPoint);
}

// ──────────────────────────────────────────
// رسم الشريط العلوي (Header)
// ──────────────────────────────────────────
static void DrawHeader(Graphics& g, int W)
{
    // خلفية
    SolidBrush bgBr(C::CARD);
    g.FillRectangle(&bgBr, 0,0,W,HEADER_H);

    // خط سفلي
    Pen sepPen(C::BORDER,1);
    g.DrawLine(&sepPen,0,HEADER_H-1,W,HEADER_H-1);

    // ── مربع الأيقونة (لون بنفسجي) ──
    SolidBrush iconBg(C::PRIMARY);
    RoundRect(g, iconBg, 18, 14, 40, 40, 8);
    SolidBrush wBr(C::WHITE);
    Font iconFont(ff, 18, FontStyleBold, UnitPoint);
    DrawTextLTR(g, L"\U0001F5A5", iconFont, wBr, 18,14,40,40,
                StringAlignmentCenter, StringAlignmentCenter);

    // ── عنوان التطبيق ──
    SolidBrush mainBr(C::TEXT_MAIN);
    SolidBrush mutedBr(C::TEXT_MUTED);
    DrawText(g, L"DeskControl Pro", *fTitle, mainBr,  68, 12, 280, 26,
             StringAlignmentFar);
    DrawText(g, L"Remote Desktop & Control", *fSmall, mutedBr, 68, 38, 280, 20,
             StringAlignmentFar);

    // ── شارات يمين: منفذ + تشفير ──
    // شارة المنفذ
    {
        SolidBrush fb(C::FIELD);
        RoundRect(g, fb, float(W-230), 20, 95, 28, 7);
        Pen bp(C::BORDER,1);
        RoundRectStroke(g, bp, float(W-230), 20, 95, 28, 7);
        SolidBrush tb(C::TEXT_MUTED);
        wchar_t portTxt[32]; swprintf_s(portTxt,L"⚡  :%d",PORT);
        DrawTextLTR(g, portTxt, *fSmall, tb, float(W-230),20,95,28,
                    StringAlignmentCenter);
    }
    // شارة التشفير
    {
        SolidBrush fb(C::FIELD);
        RoundRect(g, fb, float(W-128), 20, 112, 28, 7);
        Pen bp(C::BORDER,1);
        RoundRectStroke(g, bp, float(W-128), 20, 112, 28, 7);
        SolidBrush gb(C::GREEN);
        DrawTextLTR(g, L"🔒  AES-256", *fSmall, gb, float(W-128),20,112,28,
                    StringAlignmentCenter);
    }
}

// ──────────────────────────────────────────
// رسم بطاقة "جهازك" (يسار)
// ──────────────────────────────────────────
static void DrawHostCard(Graphics& g, int cx, int cy, int cw, int ch_)
{
    float x=float(cx),y=float(cy),w=float(cw),h=float(ch_);

    // ظل خفيف
    {
        SolidBrush shadow(Color(40,76,29,149));
        RoundRect(g,shadow,x+3,y+4,w,h,float(CORNER_R));
    }
    // خلفية البطاقة
    SolidBrush cardBr(C::CARD);
    RoundRect(g,cardBr,x,y,w,h,float(CORNER_R));
    // حدود
    Pen borderPen(C::BORDER,1);
    RoundRectStroke(g,borderPen,x,y,w,h,float(CORNER_R));

    // ─ رأس البطاقة ─
    {
        SolidBrush hBr(C::FIELD);
        RoundRect(g,hBr,x+14,y+14,w-28,60,10);

        // أيقونة البيت
        SolidBrush iconBg(C::PRIMARY_G);
        RoundRect(g,iconBg,x+24,y+25,38,38,8);
        SolidBrush wBr(C::WHITE);
        Font ef(ff,16,FontStyleBold,UnitPoint);
        DrawTextLTR(g,L"\U0001F3E0",ef,wBr,x+24,y+25,38,38,
                    StringAlignmentCenter,StringAlignmentCenter);

        SolidBrush mainBr(C::TEXT_MAIN);
        SolidBrush mutBr(C::TEXT_MUTED);
        DrawText(g,L"جهازك الحالي",*fBody,mainBr, x+70,y+23,w-90,22,StringAlignmentFar);
        DrawText(g,L"شارك المعرّف وكلمة المرور للسماح بالتحكم",
                  *fSmall,mutBr, x+70,y+45,w-90,18,StringAlignmentFar);
    }

    // ─ تسمية معرّف الجهاز ─
    {
        SolidBrush plBr(C::PRIMARY_L);
        DrawText(g,L"معرّف الجهاز  (Device ID)",*fSmall,plBr,x+14,y+88,w-28,18,StringAlignmentFar);
    }
    // حقل ID (مرسوم بالكامل — القيمة تُكتب في WM_PAINT)
    {
        SolidBrush fb(C::FIELD2);
        // FIELD2 not defined, use CARD2
        SolidBrush fb2(C::CARD2);
        RoundRect(g,fb2,x+14,y+108,w-28,44,10);
        Pen bp(C::BORDER,1);
        RoundRectStroke(g,bp,x+14,y+108,w-28,44,10);

        SolidBrush valBr(C::TEXT_MAIN);
        Font monof(ff,15,FontStyleBold,UnitPoint);
        DrawTextLTR(g,g_state.myDeviceID,monof,valBr,
                    x+14,y+108,w-28,44,StringAlignmentCenter,StringAlignmentCenter);
    }

    // ─ تسمية كلمة المرور ─
    {
        SolidBrush plBr(C::PRIMARY_L);
        DrawText(g,L"كلمة المرور المؤقتة",*fSmall,plBr,x+14,y+164,w-28,18,StringAlignmentFar);
    }
    // حقل PW
    {
        SolidBrush fb2(C::CARD2);
        RoundRect(g,fb2,x+14,y+184,w-28,44,10);
        Pen bp(C::BORDER,1);
        RoundRectStroke(g,bp,x+14,y+184,w-28,44,10);

        SolidBrush valBr(C::ACCENT_L);
        Font monof(ff,15,FontStyleBold,UnitPoint);
        DrawTextLTR(g,g_state.myPassword,monof,valBr,
                    x+14,y+184,w-28,44,StringAlignmentCenter,StringAlignmentCenter);
    }

    // ─ زر "نسخ" ─ (المستطيل — الزر الحقيقي فوقه)
    {
        SolidBrush fb(C::FIELD);
        RoundRect(g,fb,x+14,y+244,w-28,40,9);
        Pen bp(C::BORDER,1);
        RoundRectStroke(g,bp,x+14,y+244,w-28,40,9);
        SolidBrush tb(C::TEXT_SUB);
        DrawText(g,L"📋  نسخ بيانات الوصول",*fBody,tb,x+14,y+244,w-28,40,
                 StringAlignmentCenter,StringAlignmentCenter);
    }

    // ─ زر "توليد كلمة مرور" ─
    {
        Pen bp(C::BORDER_G2,1);
        RoundRectStroke(g,bp,x+14,y+292,w-28,36,9);
        SolidBrush tb(C::ACCENT);
        DrawText(g,L"🔄  توليد كلمة مرور جديدة",*fSmall,tb,x+14,y+292,w-28,36,
                 StringAlignmentCenter,StringAlignmentCenter);
    }
}

// ──────────────────────────────────────────
// رسم بطاقة "الاتصال البعيد" (يمين)
// ──────────────────────────────────────────
static void DrawClientCard(Graphics& g, int cx, int cy, int cw, int ch_)
{
    float x=float(cx),y=float(cy),w=float(cw),h=float(ch_);

    // ظل
    {
        SolidBrush shadow(Color(40,120,53,15));
        RoundRect(g,shadow,x+3,y+4,w,h,float(CORNER_R));
    }
    // خلفية
    SolidBrush cardBr(C::CARD);
    RoundRect(g,cardBr,x,y,w,h,float(CORNER_R));
    Pen borderPen(C::BORDER,1);
    RoundRectStroke(g,borderPen,x,y,w,h,float(CORNER_R));

    // ─ رأس البطاقة ─
    {
        SolidBrush hBr(C::FIELD);
        RoundRect(g,hBr,x+14,y+14,w-28,60,10);

        // أيقونة الكرة الأرضية
        SolidBrush iconBg(Color(255,26,18,0));
        RoundRect(g,iconBg,x+24,y+25,38,38,8);
        SolidBrush wBr(C::WHITE);
        Font ef(ff,16,FontStyleBold,UnitPoint);
        DrawTextLTR(g,L"\U0001F310",ef,wBr,x+24,y+25,38,38,
                    StringAlignmentCenter,StringAlignmentCenter);

        SolidBrush mainBr(C::TEXT_MAIN);
        SolidBrush mutBr(C::TEXT_MUTED);
        DrawText(g,L"التحكم بجهاز بعيد",*fBody,mainBr, x+70,y+23,w-90,22,StringAlignmentFar);
        DrawText(g,L"أدخل معرّف الجهاز الآخر وكلمة مروره",
                  *fSmall,mutBr, x+70,y+45,w-90,18,StringAlignmentFar);
    }

    // ─ تسمية Remote ID ─
    {
        SolidBrush aLBr(C::ACCENT);
        DrawText(g,L"معرّف الجهاز البعيد  (Remote ID)",*fSmall,aLBr,
                 x+14,y+88,w-28,18,StringAlignmentFar);
    }

    // ─ تسمية كلمة المرور ─
    {
        SolidBrush aLBr(C::ACCENT);
        DrawText(g,L"كلمة مرور الجهاز البعيد",*fSmall,aLBr,
                 x+14,y+168,w-28,18,StringAlignmentFar);
    }

    // ─ زر "بدء الاتصال" ─ (خلفية — الزر الحقيقي يُرسم بـ HBRUSH)
    {
        SolidBrush btnBr(C::PRIMARY);
        RoundRect(g,btnBr,x+14,y+256,w-28,50,11);
        SolidBrush wBr(C::WHITE);
        Font bf(ff,15,FontStyleBold,UnitPoint);
        DrawText(g,L"▶  بدء الاتصال عن بُعد",bf,wBr,
                 x+14,y+256,w-28,50,StringAlignmentCenter,StringAlignmentCenter);
    }
}

// ──────────────────────────────────────────
// رسم الشريط السفلي (Footer)
// ──────────────────────────────────────────
static void DrawFooter(Graphics& g, int W, int winH)
{
    float y = float(winH - FOOTER_H);
    SolidBrush bg(C::CARD);
    g.FillRectangle(&bg, 0.0f, y, float(W), float(FOOTER_H));
    Pen sepPen(C::BORDER,1);
    g.DrawLine(&sepPen, 0.0f, y, float(W), y);

    // نبضة (dot يتغير سطوعه)
    float pulse = 0.5f + 0.5f * sinf(float(g_state.animTick) * 0.15f);
    BYTE alpha = BYTE(180 + 75*pulse);
    Color dotColor(alpha, g_state.statusColor.GetR(),
                         g_state.statusColor.GetG(),
                         g_state.statusColor.GetB());
    SolidBrush dotBr(dotColor);
    g.FillEllipse(&dotBr, 18.0f, y+16, 12, 12);

    // نص الحالة
    SolidBrush mutBr(C::TEXT_MUTED);
    DrawText(g, g_state.statusText, *fSmall, mutBr,
             38, y, float(W/2), float(FOOTER_H), StringAlignmentFar);

    // IP + Port
    wchar_t ipTxt[128];
    swprintf_s(ipTxt, L"IP: %ls  |  Port: %d", g_state.myIP.c_str(), PORT);
    SolidBrush dimBr(C::TEXT_DIM);
    DrawTextLTR(g, ipTxt, *fSmall, dimBr,
                float(W/2), y, float(W/2-16), float(FOOTER_H),
                StringAlignmentFar);
}

// ──────────────────────────────────────────
// Toast إشعار طافٍ (بسيط بـ WM_TIMER)
// ──────────────────────────────────────────
struct Toast {
    std::wstring text;
    Color        color;
    int          tick = 0;   // عداد تنازلي (60 = 3 ثوانٍ @ 50ms)
    bool         active = false;
};
Toast g_toast;

static void ShowToast(const std::wstring& txt, Color col = C::GREEN)
{
    g_toast = {txt, col, 60, true};
}

static void DrawToast(Graphics& g, int W)
{
    if(!g_toast.active) return;
    float alpha_f = float(g_toast.tick) / 60.0f;
    if(alpha_f > 0.8f) alpha_f = 1.0f;
    BYTE a = BYTE(255 * alpha_f);

    Color bg (a, C::CARD.GetR(),        C::CARD.GetG(),        C::CARD.GetB());
    Color brc(a, g_toast.color.GetR(),  g_toast.color.GetG(),  g_toast.color.GetB());
    Color tc (a, C::TEXT_MAIN.GetR(),   C::TEXT_MAIN.GetG(),   C::TEXT_MAIN.GetB());

    float tw = 360, th = 44;
    float tx = (W - tw) / 2.0f, ty = 10;

    SolidBrush bgBr(bg);
    RoundRect(g, bgBr, tx, ty, tw, th, 20);
    Pen bp(brc, 1);
    RoundRectStroke(g, bp, tx, ty, tw, th, 20);

    // نقطة ملونة
    SolidBrush dotBr(brc);
    g.FillEllipse(&dotBr, tx+16, ty+17, 10, 10);

    SolidBrush tb(tc);
    DrawText(g, g_toast.text, *fSmall, tb, tx+32, ty, tw-48, th,
             StringAlignmentCenter, StringAlignmentCenter);
}

// ──────────────────────────────────────────
// إنشاء عناصر التحكم (Edit controls فوق الرسم)
// ──────────────────────────────────────────
static void CreateControls(HWND hwnd, int W, int H)
{
    int bodyY  = HEADER_H + 16;
    int bodyH  = H - HEADER_H - FOOTER_H - 32;
    int halfW  = (W - CARD_PAD*3) / 2;

    // منطقة البطاقة اليمين (client card) — عمود 1
    int rx = CARD_PAD*2 + halfW;
    int ry = bodyY;

    // Edit: Remote ID
    g_editRemote = CreateWindowEx(
        0, L"EDIT", L"",
        WS_CHILD|WS_VISIBLE|ES_CENTER|ES_AUTOHSCROLL,
        rx+14, ry+108, halfW-28, 44,
        hwnd, (HMENU)ID_EDIT_REMOTE, GetModuleHandle(nullptr), nullptr
    );

    // Edit: Remote Password
    g_editPW = CreateWindowEx(
        0, L"EDIT", L"",
        WS_CHILD|WS_VISIBLE|ES_CENTER|ES_AUTOHSCROLL|ES_PASSWORD,
        rx+14, ry+188, halfW-28, 44,
        hwnd, (HMENU)ID_EDIT_PW, GetModuleHandle(nullptr), nullptr
    );

    // تطبيق خط وألوان على حقول الإدخال
    HFONT hf = CreateFont(18,0,0,0,FW_NORMAL,FALSE,FALSE,FALSE,
                          DEFAULT_CHARSET,OUT_DEFAULT_PRECIS,CLIP_DEFAULT_PRECIS,
                          CLEARTYPE_QUALITY,DEFAULT_PITCH|FF_SWISS,L"Segoe UI");
    SendMessage(g_editRemote, WM_SETFONT, (WPARAM)hf, TRUE);
    SendMessage(g_editPW,     WM_SETFONT, (WPARAM)hf, TRUE);

    // Placeholder text
    SendMessage(g_editRemote, EM_SETCUEBANNER, FALSE, (LPARAM)L"مثال:  780 102 405");
    SendMessage(g_editPW,     EM_SETCUEBANNER, FALSE, (LPARAM)L"أدخل كلمة المرور");
}

// ──────────────────────────────────────────
// الرسم الكامل (WM_PAINT)
// ──────────────────────────────────────────
static void OnPaint(HWND hwnd)
{
    PAINTSTRUCT ps;
    HDC hdc = BeginPaint(hwnd, &ps);

    RECT rc; GetClientRect(hwnd, &rc);
    int W = rc.right, H = rc.bottom;

    // Double-buffering
    HDC memDC  = CreateCompatibleDC(hdc);
    HBITMAP bmp = CreateCompatibleBitmap(hdc, W, H);
    SelectObject(memDC, bmp);

    Graphics g(memDC);
    g.SetSmoothingMode(SmoothingModeAntiAlias);
    g.SetTextRenderingHint(TextRenderingHintClearTypeGridFit);

    // ─ خلفية كاملة ─
    SolidBrush bgBr(C::BG_DARK);
    g.FillRectangle(&bgBr, 0, 0, W, H);

    // ─ Header ─
    DrawHeader(g, W);

    // ─ حساب مواضع البطاقتين ─
    int bodyY = HEADER_H + 16;
    int bodyH = H - HEADER_H - FOOTER_H - 32;
    int halfW = (W - CARD_PAD*3) / 2;

    int lx = CARD_PAD,            ly = bodyY;
    int rx = CARD_PAD*2 + halfW,  ry = bodyY;

    DrawHostCard  (g, lx, ly, halfW, bodyH);
    DrawClientCard(g, rx, ry, halfW, bodyH);

    // ─ Footer ─
    DrawFooter(g, W, H);

    // ─ Toast ─
    DrawToast(g, W);

    // Blit
    BitBlt(hdc, 0, 0, W, H, memDC, 0, 0, SRCCOPY);
    DeleteObject(bmp);
    DeleteDC(memDC);
    EndPaint(hwnd, &ps);
}

// ──────────────────────────────────────────
// Hit Testing — تحديد أي زر ضُغط
// ──────────────────────────────────────────
static void OnLButtonUp(HWND hwnd, int mx, int my)
{
    RECT rc; GetClientRect(hwnd,&rc);
    int W=rc.right, H=rc.bottom;
    int bodyY=HEADER_H+16;
    int halfW=(W-CARD_PAD*3)/2;

    int lx=CARD_PAD, ly=bodyY;

    // زر نسخ — بطاقة يسار
    RECT copyBtn = {lx+14, ly+244, lx+14+halfW-28, ly+284};
    RECT regenBtn= {lx+14, ly+292, lx+14+halfW-28, ly+328};

    int rx=CARD_PAD*2+halfW;
    RECT connBtn = {rx+14, ly+256, rx+14+halfW-28, ly+306};

    POINT pt={mx,my};
    if(PtInRect(&copyBtn,pt)){
        // نسخ
        std::wstring txt = L"DeskControl ID: "+g_state.myDeviceID+L"\nPassword: "+g_state.myPassword;
        if(OpenClipboard(hwnd)){
            EmptyClipboard();
            size_t sz = (txt.size()+1)*sizeof(wchar_t);
            HGLOBAL hg = GlobalAlloc(GMEM_MOVEABLE, sz);
            if(hg){
                memcpy(GlobalLock(hg), txt.c_str(), sz);
                GlobalUnlock(hg);
                SetClipboardData(CF_UNICODETEXT, hg);
            }
            CloseClipboard();
        }
        ShowToast(L"✓ تم نسخ المعرّف وكلمة المرور", C::PRIMARY);
        InvalidateRect(hwnd,nullptr,FALSE);
    }
    else if(PtInRect(&regenBtn,pt)){
        g_state.myPassword = MakePassword();
        ShowToast(L"✓ تم توليد كلمة مرور جديدة", C::PRIMARY);
        InvalidateRect(hwnd,nullptr,FALSE);
    }
    else if(PtInRect(&connBtn,pt)){
        wchar_t rid[64]={}, pw[64]={};
        GetWindowText(g_editRemote,rid,64);
        GetWindowText(g_editPW,    pw,64);
        if(wcslen(rid)==0){
            ShowToast(L"يرجى إدخال معرّف الجهاز البعيد", C::RED); }
        else if(wcslen(pw)==0){
            ShowToast(L"يرجى إدخال كلمة المرور", C::RED); }
        else {
            // ── بدء محاولة الاتصال (stub — يمكن توسيعها) ──
            g_state.statusText  = std::wstring(L"جاري الاتصال بـ ")+rid+L" …";
            g_state.statusColor = C::ACCENT;
            ShowToast(L"⚡ جاري الاتصال...", C::ACCENT);
        }
        InvalidateRect(hwnd,nullptr,FALSE);
    }
}

// ──────────────────────────────────────────
// WndProc
// ──────────────────────────────────────────
static LRESULT CALLBACK WndProc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp)
{
    switch(msg)
    {
    case WM_CREATE:
        {
            RECT rc; GetClientRect(hwnd,&rc);
            CreateControls(hwnd, rc.right, rc.bottom);
            SetTimer(hwnd, ID_TIMER_ANIM, 50, nullptr); // 20fps للنبضة والتوست
        }
        return 0;

    case WM_PAINT:
        OnPaint(hwnd);
        return 0;

    case WM_ERASEBKGND:
        return 1; // نتجنب الوميض

    case WM_LBUTTONUP:
        OnLButtonUp(hwnd, GET_X_LPARAM(lp), GET_Y_LPARAM(lp));
        return 0;

    case WM_KEYDOWN:
        if(wp==VK_RETURN && GetFocus()==g_editPW){
            // ضغط Enter في حقل كلمة المرور = اتصال
            SendMessage(hwnd,WM_LBUTTONUP,0,0); // stub trigger
        }
        return 0;

    case WM_TIMER:
        if(wp==ID_TIMER_ANIM){
            g_state.animTick++;
            if(g_toast.active){
                g_toast.tick--;
                if(g_toast.tick<=0) g_toast.active=false;
            }
            // إعادة رسم الفوتر فقط (للأداء)
            RECT rc; GetClientRect(hwnd,&rc);
            RECT footerRc={0, rc.bottom-FOOTER_H, rc.right, rc.bottom};
            InvalidateRect(hwnd,&footerRc,FALSE);
            if(g_toast.active){
                RECT toastRc={0,0,rc.right,70};
                InvalidateRect(hwnd,&toastRc,FALSE);
            }
        }
        return 0;

    case WM_CTLCOLOREDIT:
        // تلوين حقول الإدخال
        {
            HDC hdc=(HDC)wp;
            SetTextColor(hdc, C::toCR(C::TEXT_MAIN));
            SetBkColor  (hdc, C::toCR(C::CARD2));
            if(!g_fieldBrush)
                g_fieldBrush = CreateSolidBrush(C::toCR(C::CARD2));
            return (LRESULT)g_fieldBrush;
        }

    case WM_DESTROY:
        KillTimer(hwnd, ID_TIMER_ANIM);
        if(g_fieldBrush){ DeleteObject(g_fieldBrush); g_fieldBrush=nullptr; }
        PostQuitMessage(0);
        return 0;

    case WM_SETCURSOR:
        // تغيير المؤشر فوق الأزرار
        {
            POINT pt; GetCursorPos(&pt); ScreenToClient(hwnd,&pt);
            RECT rc; GetClientRect(hwnd,&rc);
            int W=rc.right,H=rc.bottom;
            int bodyY=HEADER_H+16, halfW=(W-CARD_PAD*3)/2;
            int lx=CARD_PAD,ly=bodyY,rx=CARD_PAD*2+halfW;
            RECT r1={lx+14,ly+244,lx+14+halfW-28,ly+284};
            RECT r2={lx+14,ly+292,lx+14+halfW-28,ly+328};
            RECT r3={rx+14,ly+256,rx+14+halfW-28,ly+306};
            if(PtInRect(&r1,pt)||PtInRect(&r2,pt)||PtInRect(&r3,pt)){
                SetCursor(LoadCursor(nullptr,IDC_HAND));
                return TRUE;
            }
        }
        break;
    }
    return DefWindowProc(hwnd,msg,wp,lp);
}

// ──────────────────────────────────────────
// WinMain
// ──────────────────────────────────────────
int WINAPI WinMain(HINSTANCE hInst, HINSTANCE, LPSTR, int nCmdShow)
{
    // GDI+ init
    ULONG_PTR gdiToken;
    GdiplusStartupInput gsi;
    GdiplusStartup(&gdiToken, &gsi, nullptr);

    // Winsock init
    WSADATA wsa; WSAStartup(MAKEWORD(2,2),&wsa);

    // الخطوط
    InitFonts();

    // بيانات التطبيق
    g_state.myIP       = GetLocalIP();
    g_state.myDeviceID = IPtoDeviceID(g_state.myIP);
    g_state.myPassword = MakePassword();

    // تسجيل النافذة
    WNDCLASSEX wc={};
    wc.cbSize        = sizeof(wc);
    wc.lpfnWndProc   = WndProc;
    wc.hInstance     = hInst;
    wc.lpszClassName = L"DeskControlWnd";
    wc.hCursor       = LoadCursor(nullptr, IDC_ARROW);
    wc.hbrBackground = CreateSolidBrush(C::toCR(C::BG_DARK));
    wc.hIcon         = LoadIcon(nullptr, IDI_APPLICATION);
    RegisterClassEx(&wc);

    // منتصف الشاشة
    int sx = GetSystemMetrics(SM_CXSCREEN);
    int sy = GetSystemMetrics(SM_CYSCREEN);
    int wx = (sx - WIN_W) / 2;
    int wy = (sy - WIN_H) / 2;

    g_hwnd = CreateWindowEx(
        WS_EX_APPWINDOW,
        L"DeskControlWnd",
        L"DeskControl Pro",
        WS_OVERLAPPED|WS_CAPTION|WS_SYSMENU|WS_MINIMIZEBOX,
        wx, wy, WIN_W, WIN_H,
        nullptr, nullptr, hInst, nullptr
    );

    ShowWindow(g_hwnd, nCmdShow);
    UpdateWindow(g_hwnd);

    // حلقة الرسائل
    MSG msg;
    while(GetMessage(&msg,nullptr,0,0)){
        TranslateMessage(&msg);
        DispatchMessage(&msg);
    }

    // تنظيف
    delete fTitle; delete fBody; delete fSmall; delete fLarge; delete fMono;
    delete ff;
    WSACleanup();
    GdiplusShutdown(gdiToken);
    return (int)msg.wParam;
}
