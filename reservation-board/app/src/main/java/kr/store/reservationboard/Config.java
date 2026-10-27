package kr.store.reservationboard;

import android.content.Context;
import android.content.SharedPreferences;

import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

/** 사장님이 설정 화면에서 고른 값들. 출처(네이버, 자사앱)마다 이름·앱·키워드를 따로 저장합니다. */
final class Config {
    static final int SOURCES = 2;
    static final int[] COLORS = {0xFF03C75A, 0xFF3B82F6};
    private static final String[] DEFAULT_NAMES = {"네이버", "자사앱"};
    private static final float[] TEXT_SCALES = {1f, 1.25f, 1.5f};

    private Config() {}

    private static SharedPreferences prefs(Context c) {
        return c.getApplicationContext().getSharedPreferences("board", Context.MODE_PRIVATE);
    }

    /** 패키지별로 마지막으로 알림을 보낸 시각. 설정에서 어떤 앱인지 찾기 쉽게 해 줍니다. */
    private static SharedPreferences seenPrefs(Context c) {
        return c.getApplicationContext().getSharedPreferences("seen", Context.MODE_PRIVATE);
    }

    static String name(Context c, int src) {
        String n = prefs(c).getString("name" + src, "").trim();
        return n.isEmpty() ? DEFAULT_NAMES[src] : n;
    }

    static void setName(Context c, int src, String name) {
        prefs(c).edit().putString("name" + src, name.trim()).apply();
    }

    static Set<String> packages(Context c, int src) {
        return new HashSet<>(prefs(c).getStringSet("pkgs" + src, Collections.emptySet()));
    }

    static void setPackages(Context c, int src, Set<String> pkgs) {
        prefs(c).edit().putStringSet("pkgs" + src, new HashSet<>(pkgs)).apply();
    }

    static boolean anyPackages(Context c) {
        for (int i = 0; i < SOURCES; i++) {
            if (!packages(c, i).isEmpty()) return true;
        }
        return false;
    }

    /** 알림을 보낸 앱이 어느 출처인지. 해당 없으면 -1. */
    static int sourceFor(Context c, String pkg) {
        for (int i = 0; i < SOURCES; i++) {
            if (packages(c, i).contains(pkg)) return i;
        }
        return -1;
    }

    static String keywords(Context c, int src) {
        return prefs(c).getString("kw" + src, "");
    }

    static void setKeywords(Context c, int src, String keywords) {
        prefs(c).edit().putString("kw" + src, keywords.trim()).apply();
    }

    /** 키워드가 비어 있으면 모든 알림을 통과시키고, 있으면 하나라도 포함된 알림만 통과시킵니다. */
    static boolean matches(Context c, int src, String text) {
        boolean any = false;
        for (String k : keywords(c, src).split(",")) {
            k = k.trim();
            if (k.isEmpty()) continue;
            any = true;
            if (text.contains(k)) return true;
        }
        return !any;
    }

    static boolean sound(Context c) {
        return prefs(c).getBoolean("sound", true);
    }

    static void setSound(Context c, boolean on) {
        prefs(c).edit().putBoolean("sound", on).apply();
    }

    static boolean voice(Context c) {
        return prefs(c).getBoolean("voice", true);
    }

    static void setVoice(Context c, boolean on) {
        prefs(c).edit().putBoolean("voice", on).apply();
    }

    static int textSize(Context c) {
        return Math.max(0, Math.min(TEXT_SCALES.length - 1, prefs(c).getInt("textSize", 1)));
    }

    static void setTextSize(Context c, int size) {
        prefs(c).edit().putInt("textSize", size).apply();
    }

    static float textScale(Context c) {
        return TEXT_SCALES[textSize(c)];
    }

    static void markSeen(Context c, String pkg) {
        seenPrefs(c).edit().putLong(pkg, System.currentTimeMillis()).apply();
    }

    static Map<String, Long> seen(Context c) {
        Map<String, Long> out = new HashMap<>();
        for (Map.Entry<String, ?> e : seenPrefs(c).getAll().entrySet()) {
            if (e.getValue() instanceof Long) out.put(e.getKey(), (Long) e.getValue());
        }
        return out;
    }
}
