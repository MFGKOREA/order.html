package kr.store.reservationboard;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.provider.Settings;
import android.webkit.JavascriptInterface;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.text.Collator;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

/**
 * 화면(board.js)이 부르는 창구. window.Android 로 보입니다.
 * 이 메서드들은 화면 스레드가 아닌 곳에서 불리므로, 화면을 여는 일은 MainActivity에 넘깁니다.
 */
final class Bridge {
    /** 화면에는 최근 이틀 치를 보여 줍니다. */
    static final long SHOW_WINDOW = 48L * 60 * 60 * 1000;

    private final MainActivity activity;
    private final Context ctx;

    Bridge(MainActivity activity) {
        this.activity = activity;
        this.ctx = activity.getApplicationContext();
    }

    @JavascriptInterface
    public String state() throws JSONException {
        JSONObject o = new JSONObject();
        o.put("listener", new JSONObject()
                .put("enabled", Ui.listenerEnabled(ctx))
                .put("connected", Board.connected));
        o.put("settings", new JSONObject()
                .put("sound", Config.sound(ctx))
                .put("voice", Config.voice(ctx))
                .put("textSize", Config.textSize(ctx)));

        PackageManager pm = ctx.getPackageManager();
        Set<String> iconPkgs = new HashSet<>();
        JSONArray sources = new JSONArray();
        for (int i = 0; i < Config.SOURCES; i++) {
            JSONArray pkgs = new JSONArray();
            for (String pkg : Config.packages(ctx, i)) {
                pkgs.put(new JSONObject().put("pkg", pkg).put("label", appLabel(pm, pkg)));
                iconPkgs.add(pkg);
            }
            sources.put(new JSONObject()
                    .put("name", Config.name(ctx, i))
                    .put("keywords", Config.keywords(ctx, i))
                    .put("packages", pkgs));
        }
        o.put("sources", sources);

        JSONArray entries = new JSONArray();
        for (Entry e : Store.get(ctx).recent(System.currentTimeMillis() - SHOW_WINDOW, -1)) {
            entries.put(new JSONObject()
                    .put("id", e.id)
                    .put("posted", e.posted)
                    .put("source", e.source)
                    .put("pkg", e.pkg)
                    .put("title", e.title)
                    .put("body", e.body)
                    .put("isNew", e.isNew));
            iconPkgs.add(e.pkg);
        }
        o.put("entries", entries);

        iconPkgs.remove(ctx.getPackageName());
        JSONObject icons = new JSONObject();
        for (String pkg : iconPkgs) icons.put(pkg, MainActivity.iconUrl(pkg));
        o.put("icons", icons);
        return o.toString();
    }

    /** 앱 고르기 목록. 최근에 알림을 보낸 앱이 맨 위에 옵니다. */
    @JavascriptInterface
    public String apps() throws JSONException {
        PackageManager pm = ctx.getPackageManager();
        Map<String, Long> seen = Config.seen(ctx);
        Set<String> pkgs = new LinkedHashSet<>(seen.keySet());
        Intent launcher = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        for (ResolveInfo ri : pm.queryIntentActivities(launcher, 0)) pkgs.add(ri.activityInfo.packageName);
        pkgs.remove(ctx.getPackageName());

        List<JSONObject> list = new ArrayList<>();
        for (String pkg : pkgs) {
            list.add(new JSONObject()
                    .put("pkg", pkg)
                    .put("label", appLabel(pm, pkg))
                    .put("icon", MainActivity.iconUrl(pkg))
                    .put("seen", seen.getOrDefault(pkg, 0L)));
        }
        Collator collator = Collator.getInstance(Locale.KOREAN);
        list.sort((a, b) -> {
            int bySeen = Long.compare(b.optLong("seen"), a.optLong("seen"));
            return bySeen != 0 ? bySeen : collator.compare(a.optString("label"), b.optString("label"));
        });
        return new JSONArray(list).toString();
    }

    @JavascriptInterface
    public void ack(String id) {
        Store.get(ctx).markSeen(Long.parseLong(id));
    }

    @JavascriptInterface
    public void ackAll() {
        Store.get(ctx).markAllSeen();
    }

    @JavascriptInterface
    public void open(String id) {
        long entryId = Long.parseLong(id);
        Store.get(ctx).markSeen(entryId);
        activity.runOnUiThread(() -> activity.openEntry(entryId));
    }

    @JavascriptInterface
    public void test() {
        activity.runOnUiThread(activity::addTestEntry);
    }

    @JavascriptInterface
    public void clear() {
        Store.get(ctx).clear();
        Board.intents.clear();
    }

    @JavascriptInterface
    public void saveSource(String index, String json) throws JSONException {
        int src = Integer.parseInt(index);
        JSONObject o = new JSONObject(json);
        Config.setName(ctx, src, o.optString("name"));
        Config.setKeywords(ctx, src, o.optString("keywords"));
    }

    /** 한 앱은 한 출처에만 속하게 합니다. */
    @JavascriptInterface
    public void setPackages(String index, String json) throws JSONException {
        int src = Integer.parseInt(index);
        JSONArray arr = new JSONArray(json);
        Set<String> picked = new HashSet<>();
        for (int i = 0; i < arr.length(); i++) picked.add(arr.getString(i));
        for (int other = 0; other < Config.SOURCES; other++) {
            if (other == src) continue;
            Set<String> o = Config.packages(ctx, other);
            if (o.removeAll(picked)) Config.setPackages(ctx, other, o);
        }
        Config.setPackages(ctx, src, picked);
    }

    @JavascriptInterface
    public void setSetting(String key, String value) {
        switch (key) {
            case "sound": Config.setSound(ctx, Boolean.parseBoolean(value)); break;
            case "voice": Config.setVoice(ctx, Boolean.parseBoolean(value)); break;
            case "textSize": Config.setTextSize(ctx, Integer.parseInt(value)); break;
            default: break;
        }
    }

    @JavascriptInterface
    public void openListenerSettings() {
        activity.runOnUiThread(() -> activity.startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
    }

    @JavascriptInterface
    public void openBatterySettings() {
        activity.runOnUiThread(() -> activity.startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)));
    }

    static String appLabel(PackageManager pm, String pkg) {
        try {
            return pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString();
        } catch (PackageManager.NameNotFoundException e) {
            return pkg;
        }
    }
}
