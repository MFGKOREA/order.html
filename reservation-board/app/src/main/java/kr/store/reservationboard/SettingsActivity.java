package kr.store.reservationboard;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.content.pm.ResolveInfo;
import android.os.Bundle;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.widget.CompoundButton;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.ScrollView;
import android.widget.Switch;
import android.widget.TextView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

/** 어떤 앱의 알림을 모을지, 소리·글자 크기 등을 정하는 화면. */
public class SettingsActivity extends Activity {
    private final EditText[] names = new EditText[Config.SOURCES];
    private final EditText[] keywords = new EditText[Config.SOURCES];
    private final TextView[] appButtons = new TextView[Config.SOURCES];
    private TextView permission;
    private LinearLayout column;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Ui.BG);
        Ui.fitSystemBars(scroll);
        column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        int pad = Ui.dp(this, 24);
        column.setPadding(pad, Ui.dp(this, 16), pad, pad * 2);
        scroll.addView(column);

        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        TextView back = Ui.button(this, "←  돌아가기", Ui.CHIP);
        back.setOnClickListener(v -> finish());
        header.addView(back);
        TextView title = Ui.text(this, "설정", 26, Ui.TEXT, true);
        title.setPadding(Ui.dp(this, 20), 0, 0, 0);
        header.addView(title);
        column.addView(header);

        section("1. 알림 접근 권한", Ui.TEXT);
        permission = Ui.text(this, "", 18, Ui.TEXT, true);
        column.addView(permission);
        action("알림 접근 설정 열기",
                v -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        hint("목록에서 '예약 알림판'을 켜 주세요.\n"
                + "스위치가 회색으로 막혀 있으면: 태블릿 설정 → 애플리케이션 → 예약 알림판 → "
                + "오른쪽 위 ⋮ → '제한된 설정 허용'을 누른 뒤 다시 켜 주세요.");

        for (int i = 0; i < Config.SOURCES; i++) {
            final int src = i;
            section((i + 2) + ". 예약 출처 " + (i + 1), Config.COLORS[i]);
            label("화면에 표시할 이름");
            names[i] = input(Config.name(this, i), "예: 네이버");
            label("알림을 읽어올 앱");
            appButtons[i] = action("", v -> pickApps(src));
            appButtons[i].setGravity(Gravity.CENTER_VERTICAL | Gravity.START);
            label("키워드 (선택)");
            keywords[i] = input(Config.keywords(this, i), "비워 두면 이 앱의 알림을 모두 표시 · 예: 예약");
            hint("쉼표로 여러 개 넣을 수 있어요 (예: 예약, 주문). 리뷰·광고 알림까지 섞여 보이면 '예약'을 넣어 주세요.");
        }

        section((Config.SOURCES + 2) + ". 알림 방식", Ui.TEXT);
        toggle("새 예약이 오면 알림음 (알람 볼륨으로 울려요)", Config.sound(this),
                (b, on) -> Config.setSound(this, on));
        toggle("음성 안내 (예: \"네이버 새 예약 알림\")", Config.voice(this),
                (b, on) -> Config.setVoice(this, on));
        label("글자 크기");
        RadioGroup sizes = new RadioGroup(this);
        sizes.setOrientation(RadioGroup.HORIZONTAL);
        String[] sizeNames = {"보통", "크게", "아주 크게"};
        for (int i = 0; i < sizeNames.length; i++) {
            RadioButton rb = new RadioButton(this);
            rb.setId(View.generateViewId());
            rb.setText(sizeNames[i]);
            rb.setTextSize(18);
            rb.setTextColor(Ui.TEXT);
            rb.setPadding(0, 0, Ui.dp(this, 24), 0);
            sizes.addView(rb);
            if (i == Config.textSize(this)) rb.setChecked(true);
            final int size = i;
            rb.setOnCheckedChangeListener((b, on) -> {
                if (on) Config.setTextSize(this, size);
            });
        }
        column.addView(sizes);

        section((Config.SOURCES + 3) + ". 오래 켜 두기", Ui.TEXT);
        action("배터리 최적화 설정 열기",
                v -> startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS)));
        hint("목록에서 '예약 알림판'을 '제한 없음' 또는 '최적화 안 함'으로 바꿔 주세요. "
                + "그래야 하루 종일 켜 두어도 알림을 놓치지 않아요. 태블릿은 충전기에 꽂아 두는 걸 추천해요.");

        section((Config.SOURCES + 4) + ". 기록", Ui.TEXT);
        action("기록 모두 지우기", v -> new AlertDialog.Builder(this)
                .setMessage("알림판의 기록을 모두 지울까요? (네이버·자사앱의 실제 예약은 지워지지 않아요)")
                .setPositiveButton("지우기", (d, w) -> {
                    Store.get(this).clear();
                    Board.intents.clear();
                    Toast.makeText(this, "기록을 지웠어요.", Toast.LENGTH_SHORT).show();
                })
                .setNegativeButton("취소", null)
                .show());
        hint("기록은 이 태블릿 안에만 저장되고 일주일이 지나면 자동으로 지워져요.");

        setContentView(scroll);
    }

    @Override
    protected void onResume() {
        super.onResume();
        boolean enabled = Ui.listenerEnabled(this);
        permission.setText(enabled ? "● 허용됨" : "● 허용 안 됨 — 아래 버튼을 눌러 켜 주세요");
        permission.setTextColor(enabled ? Ui.OK : Ui.WARN);
        updateAppButtons();
    }

    @Override
    protected void onPause() {
        super.onPause();
        for (int i = 0; i < Config.SOURCES; i++) {
            Config.setName(this, i, names[i].getText().toString());
            Config.setKeywords(this, i, keywords[i].getText().toString());
        }
    }

    private void updateAppButtons() {
        PackageManager pm = getPackageManager();
        for (int i = 0; i < Config.SOURCES; i++) {
            List<String> labels = new ArrayList<>();
            for (String pkg : Config.packages(this, i)) labels.add(appLabel(pm, pkg));
            appButtons[i].setText(labels.isEmpty() ? "선택 안 됨 — 눌러서 고르기" : String.join(", ", labels));
        }
    }

    /** 최근에 알림을 보낸 앱을 맨 위에 보여 줘서, 어떤 앱이 예약 알림을 보내는지 쉽게 찾게 합니다. */
    private void pickApps(int src) {
        PackageManager pm = getPackageManager();
        Map<String, Long> seen = Config.seen(this);
        Set<String> pkgs = new HashSet<>(seen.keySet());
        Intent launcher = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        for (ResolveInfo ri : pm.queryIntentActivities(launcher, 0)) pkgs.add(ri.activityInfo.packageName);
        pkgs.remove(getPackageName());

        List<String> order = new ArrayList<>(pkgs);
        List<String> plain = new ArrayList<>();
        for (String pkg : order) plain.add(appLabel(pm, pkg));
        Map<String, String> labelOf = new java.util.HashMap<>();
        for (int i = 0; i < order.size(); i++) labelOf.put(order.get(i), plain.get(i));
        order.sort((a, b) -> {
            long sa = seen.getOrDefault(a, 0L), sb = seen.getOrDefault(b, 0L);
            if (sa != sb) return Long.compare(sb, sa);
            return labelOf.get(a).compareTo(labelOf.get(b));
        });

        Set<String> chosen = Config.packages(this, src);
        CharSequence[] labels = new CharSequence[order.size()];
        boolean[] checked = new boolean[order.size()];
        long now = System.currentTimeMillis();
        for (int i = 0; i < order.size(); i++) {
            String pkg = order.get(i);
            Long at = seen.get(pkg);
            labels[i] = labelOf.get(pkg) + (at == null ? "" : "   · 최근 알림 " + ago(now - at));
            checked[i] = chosen.contains(pkg);
        }

        new AlertDialog.Builder(this)
                .setTitle(Config.name(this, src) + " 예약 알림을 보내는 앱")
                .setMultiChoiceItems(labels, checked, (d, which, on) -> checked[which] = on)
                .setPositiveButton("저장", (d, w) -> {
                    Set<String> picked = new HashSet<>();
                    for (int i = 0; i < order.size(); i++) {
                        if (checked[i]) picked.add(order.get(i));
                    }
                    // 한 앱은 한 출처에만 속하게 합니다.
                    for (int other = 0; other < Config.SOURCES; other++) {
                        if (other == src) continue;
                        Set<String> o = Config.packages(this, other);
                        if (o.removeAll(picked)) Config.setPackages(this, other, o);
                    }
                    Config.setPackages(this, src, picked);
                    updateAppButtons();
                })
                .setNegativeButton("취소", null)
                .show();
    }

    private static String appLabel(PackageManager pm, String pkg) {
        try {
            return pm.getApplicationLabel(pm.getApplicationInfo(pkg, 0)).toString();
        } catch (PackageManager.NameNotFoundException e) {
            return pkg;
        }
    }

    private static String ago(long ms) {
        long min = ms / 60_000;
        if (min < 1) return "방금";
        if (min < 60) return min + "분 전";
        long hours = min / 60;
        if (hours < 24) return hours + "시간 전";
        return (hours / 24) + "일 전";
    }

    // ---- 레이아웃 도우미 ----

    private void section(String title, int color) {
        TextView t = Ui.text(this, title, 22, color, true);
        t.setPadding(0, Ui.dp(this, 32), 0, Ui.dp(this, 8));
        column.addView(t);
    }

    private void label(String s) {
        TextView t = Ui.text(this, s, 16, Ui.SUB, true);
        t.setPadding(0, Ui.dp(this, 12), 0, Ui.dp(this, 4));
        column.addView(t);
    }

    private void hint(String s) {
        TextView t = Ui.text(this, s, 15, Ui.SUB, false);
        t.setPadding(0, Ui.dp(this, 8), 0, 0);
        t.setLineSpacing(0, 1.2f);
        column.addView(t);
    }

    private EditText input(String value, String hintText) {
        EditText e = new EditText(this);
        e.setText(value);
        e.setHint(hintText);
        e.setSingleLine(true);
        e.setTextSize(18);
        e.setTextColor(Ui.TEXT);
        e.setHintTextColor(0xFF6B7480);
        column.addView(e, new LinearLayout.LayoutParams(-1, -2));
        return e;
    }

    private TextView action(String label, View.OnClickListener onClick) {
        TextView b = Ui.button(this, label, Ui.CHIP);
        b.setOnClickListener(onClick);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-1, -2);
        lp.topMargin = Ui.dp(this, 8);
        column.addView(b, lp);
        return b;
    }

    private void toggle(String label, boolean on, CompoundButton.OnCheckedChangeListener listener) {
        Switch s = new Switch(this);
        s.setText(label);
        s.setTextSize(18);
        s.setTextColor(Ui.TEXT);
        s.setChecked(on);
        s.setOnCheckedChangeListener(listener);
        s.setPadding(0, Ui.dp(this, 12), 0, Ui.dp(this, 12));
        column.addView(s, new LinearLayout.LayoutParams(-1, -2));
    }
}
