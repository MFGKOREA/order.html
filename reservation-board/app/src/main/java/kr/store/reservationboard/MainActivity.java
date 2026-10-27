package kr.store.reservationboard;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.app.ActivityOptions;
import android.app.PendingIntent;
import android.content.ComponentName;
import android.content.Intent;
import android.graphics.Bitmap;
import android.graphics.Canvas;
import android.graphics.drawable.Drawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.service.notification.NotificationListenerService;
import android.util.LruCache;
import android.view.WindowManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.Toast;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.util.Collections;

/**
 * 알림판 화면. 화면 자체는 assets/board 의 웹 페이지이고, 이 액티비티는 그 페이지를 띄우고
 * 알림 수신 서비스와 이어 줍니다. 영업 중 켜 두는 화면이라 꺼지지 않게 합니다.
 */
public class MainActivity extends Activity implements Board.Listener {
    private static final String HOST = "board.local";
    private static final String BASE = "https://" + HOST + "/";
    private static final long KEEP_WINDOW = 7L * 24 * 60 * 60 * 1000;

    private final LruCache<String, byte[]> iconCache = new LruCache<>(64);
    private WebView web;
    private int testSource;

    static String iconUrl(String pkg) {
        return BASE + "icon/" + pkg;
    }

    @SuppressLint("SetJavaScriptEnabled")
    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);

        web = new WebView(this);
        web.setBackgroundColor(0xFFF6F7F8);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        // 글자 크기는 알림판 설정에서 따로 정하므로 태블릿의 글꼴 배율에 끌려가지 않게 합니다.
        s.setTextZoom(100);
        web.addJavascriptInterface(new Bridge(this), "Android");
        web.setWebChromeClient(new WebChromeClient());
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                return serve(request.getUrl());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !HOST.equals(request.getUrl().getHost());
            }
        });

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(0xFFF6F7F8);
        root.addView(web, new FrameLayout.LayoutParams(-1, -1));
        Ui.fitSystemBars(root);
        setContentView(root);
        web.loadUrl(BASE + "index.html");
    }

    @Override
    protected void onResume() {
        super.onResume();
        Board.setListener(this);
        if (Ui.listenerEnabled(this)) {
            NotificationListenerService.requestRebind(new ComponentName(this, ReservationListenerService.class));
        }
        Store.get(this).purgeBefore(System.currentTimeMillis() - KEEP_WINDOW);
        js("board.refresh()");
    }

    @Override
    protected void onPause() {
        super.onPause();
        Board.setListener(null);
    }

    @Override
    @SuppressWarnings("deprecation")
    public void onBackPressed() {
        if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onDestroy() {
        web.destroy();
        super.onDestroy();
    }

    // ---- Board.Listener ----

    @Override
    public void onEntry(Entry e) {
        js("board.onEntry(" + e.id + "," + e.source + ")");
    }

    @Override
    public void onStatus() {
        js("board.refresh()");
    }

    private void js(String call) {
        if (web != null) web.evaluateJavascript("window.board && " + call, null);
    }

    // ---- 화면에서 부르는 동작 ----

    /** 원래 앱(네이버, 자사앱)의 그 예약 화면을 엽니다. 알림이 이미 사라졌으면 앱 첫 화면을 엽니다. */
    void openEntry(long id) {
        PendingIntent pi = Board.intents.get(id);
        if (pi != null) {
            try {
                if (Build.VERSION.SDK_INT >= 34) {
                    ActivityOptions options = ActivityOptions.makeBasic();
                    options.setPendingIntentBackgroundActivityStartMode(
                            ActivityOptions.MODE_BACKGROUND_ACTIVITY_START_ALLOWED);
                    pi.send(this, 0, null, null, null, null, options.toBundle());
                } else {
                    pi.send();
                }
                return;
            } catch (PendingIntent.CanceledException ignored) {
                // 아래에서 앱 첫 화면을 엽니다.
            }
        }
        String pkg = null;
        for (Entry e : Store.get(this).recent(0, -1)) {
            if (e.id == id) pkg = e.pkg;
        }
        if (pkg == null || pkg.equals(getPackageName())) return;
        Intent launch = getPackageManager().getLaunchIntentForPackage(pkg);
        if (launch != null) {
            startActivity(launch);
        } else {
            Toast.makeText(this, "이 앱을 열 수 없어요.", Toast.LENGTH_SHORT).show();
        }
    }

    /** 설치 후 소리·화면 깜빡임이 잘 되는지 확인하는 가짜 예약. 출처를 번갈아 넣습니다. */
    void addTestEntry() {
        int src = testSource;
        testSource = (testSource + 1) % Config.SOURCES;
        long now = System.currentTimeMillis();
        java.text.SimpleDateFormat f = new java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.KOREAN);
        Entry e = Store.get(this).insert(now, src, getPackageName(),
                "[테스트] 홍길동님 예약",
                "오늘 19:00 · 4명\n테스트 알림이에요. (" + f.format(new java.util.Date(now)) + ")");
        if (e == null) return;
        Alerter.get(this).alert(src);
        onEntry(e);
    }

    // ---- 페이지와 앱 아이콘 제공 ----

    private WebResourceResponse serve(Uri uri) {
        if (!HOST.equals(uri.getHost()) || uri.getPath() == null) return null;
        String path = uri.getPath();
        if (path.startsWith("/icon/")) {
            byte[] png = icon(path.substring("/icon/".length()));
            return png == null ? notFound() : new WebResourceResponse("image/png", null, new ByteArrayInputStream(png));
        }
        if (path.equals("/")) path = "/index.html";
        try {
            InputStream in = getAssets().open("board" + path);
            String mime = mimeOf(path);
            return new WebResourceResponse(mime, mime.startsWith("font/") ? null : "utf-8", in);
        } catch (IOException e) {
            return notFound();
        }
    }

    private byte[] icon(String pkg) {
        byte[] cached = iconCache.get(pkg);
        if (cached != null) return cached;
        try {
            Drawable d = getPackageManager().getApplicationIcon(pkg);
            int size = 96;
            Bitmap b = Bitmap.createBitmap(size, size, Bitmap.Config.ARGB_8888);
            d.setBounds(0, 0, size, size);
            d.draw(new Canvas(b));
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            b.compress(Bitmap.CompressFormat.PNG, 100, out);
            byte[] png = out.toByteArray();
            iconCache.put(pkg, png);
            return png;
        } catch (Exception e) {
            return null;
        }
    }

    private static WebResourceResponse notFound() {
        return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found",
                Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
    }

    private static String mimeOf(String path) {
        if (path.endsWith(".html")) return "text/html";
        if (path.endsWith(".css")) return "text/css";
        if (path.endsWith(".js")) return "application/javascript";
        if (path.endsWith(".woff2")) return "font/woff2";
        if (path.endsWith(".svg")) return "image/svg+xml";
        if (path.endsWith(".png")) return "image/png";
        return "application/octet-stream";
    }
}
