package kr.store.reservationboard;

import android.animation.Animator;
import android.animation.AnimatorListenerAdapter;
import android.animation.ObjectAnimator;
import android.app.Activity;
import android.app.ActivityOptions;
import android.app.PendingIntent;
import android.content.ComponentName;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.service.notification.NotificationListenerService;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.BaseAdapter;
import android.widget.FrameLayout;
import android.widget.HorizontalScrollView;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;
import android.widget.Toast;

import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Calendar;
import java.util.Date;
import java.util.List;
import java.util.Locale;

/** 네이버·자사앱 예약 알림을 한 화면에 모아 보여 주는 알림판. 영업 중 켜 두는 화면입니다. */
public class MainActivity extends Activity implements Board.Listener {
    /** 화면에는 최근 이틀 치를 보여 주고, 기록은 일주일 뒤 지웁니다. */
    private static final long SHOW_WINDOW = 48L * 60 * 60 * 1000;
    private static final long KEEP_WINDOW = 7L * 24 * 60 * 60 * 1000;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final List<Entry> items = new ArrayList<>();
    private final TextView[] tabs = new TextView[Config.SOURCES + 1];
    private final SimpleDateFormat clockFormat = new SimpleDateFormat("M월 d일 (E)  HH:mm", Locale.KOREAN);
    private final SimpleDateFormat timeFormat = new SimpleDateFormat("HH:mm", Locale.KOREAN);
    private final SimpleDateFormat dateTimeFormat = new SimpleDateFormat("M/d HH:mm", Locale.KOREAN);

    private int filter = -1;
    private int today = -1;
    private int testSource;
    private float scale = 1f;
    private TextView clock, status, banner, empty, ack;
    private View flash;
    private ObjectAnimator flashAnim;
    private EntryAdapter adapter;
    private ListView list;

    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            updateClock();
            handler.postDelayed(this, 10_000);
        }
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        setContentView(buildLayout());
    }

    @Override
    protected void onResume() {
        super.onResume();
        scale = Config.textScale(this);
        Board.setListener(this);
        if (Ui.listenerEnabled(this)) {
            NotificationListenerService.requestRebind(new ComponentName(this, ReservationListenerService.class));
        }
        Store.get(this).purgeBefore(System.currentTimeMillis() - KEEP_WINDOW);
        refresh();
        onStatus();
        handler.post(tick);
    }

    @Override
    protected void onPause() {
        super.onPause();
        Board.setListener(null);
        handler.removeCallbacks(tick);
    }

    // ---- Board.Listener ----

    @Override
    public void onEntry(Entry e) {
        refresh();
        list.setSelection(0);
        flash(Config.COLORS[e.source]);
    }

    @Override
    public void onStatus() {
        boolean enabled = Ui.listenerEnabled(this);
        boolean receiving = enabled && Board.connected;
        status.setText(receiving ? "● 수신 중" : "● 수신 안 됨");
        status.setTextColor(receiving ? Ui.OK : Ui.WARN);

        if (!enabled) {
            showBanner("⚠  알림 접근 권한이 꺼져 있어요. 여기를 눌러 '예약 알림판'을 켜 주세요.",
                    v -> startActivity(new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS)));
        } else if (!Config.anyPackages(this)) {
            showBanner("⚙  설정에서 네이버·자사앱이 어떤 앱인지 골라 주세요. (여기를 누르세요)",
                    v -> startActivity(new Intent(this, SettingsActivity.class)));
        } else {
            banner.setVisibility(View.GONE);
        }
    }

    // ---- 화면 갱신 ----

    private void refresh() {
        long now = System.currentTimeMillis();
        Store store = Store.get(this);
        items.clear();
        items.addAll(store.recent(now - SHOW_WINDOW, filter));
        adapter.notifyDataSetChanged();

        int[] counts = store.countsSince(startOfToday());
        int total = 0;
        for (int c : counts) total += c;
        tabs[0].setText("전체  " + total);
        for (int i = 0; i < Config.SOURCES; i++) {
            tabs[i + 1].setText(Config.name(this, i) + "  " + counts[i]);
        }
        for (int i = 0; i < tabs.length; i++) {
            boolean selected = filter == i - 1;
            int color = i == 0 ? Ui.TEXT : Config.COLORS[i - 1];
            tabs[i].setBackground(Ui.round(this, selected ? color : Ui.CHIP, 26));
            tabs[i].setTextColor(selected ? (i == 0 ? Ui.BG : Ui.TEXT) : Ui.TEXT);
        }

        int fresh = store.newCount();
        ack.setVisibility(fresh > 0 ? View.VISIBLE : View.GONE);
        ack.setText("✓  모두 확인 (" + fresh + ")");
        empty.setVisibility(items.isEmpty() ? View.VISIBLE : View.GONE);
    }

    private void updateClock() {
        Calendar cal = Calendar.getInstance();
        clock.setText(clockFormat.format(cal.getTime()));
        int day = cal.get(Calendar.DAY_OF_YEAR);
        if (today != -1 && today != day) refresh();
        today = day;
    }

    private void flash(int color) {
        if (flashAnim != null) flashAnim.cancel();
        flash.setBackgroundColor(color);
        flash.setAlpha(0f);
        flash.setVisibility(View.VISIBLE);
        flashAnim = ObjectAnimator.ofFloat(flash, View.ALPHA, 0f, 0.5f);
        flashAnim.setDuration(350);
        flashAnim.setRepeatCount(7);
        flashAnim.setRepeatMode(ObjectAnimator.REVERSE);
        flashAnim.addListener(new AnimatorListenerAdapter() {
            @Override
            public void onAnimationEnd(Animator animation) {
                flash.setAlpha(0f);
                flash.setVisibility(View.GONE);
            }
        });
        flashAnim.start();
    }

    private void showBanner(String message, View.OnClickListener onClick) {
        banner.setText(message);
        banner.setOnClickListener(onClick);
        banner.setVisibility(View.VISIBLE);
    }

    private void open(Entry e) {
        Store.get(this).markSeen(e.id);
        refresh();
        PendingIntent pi = Board.intents.get(e.id);
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
                // 원래 알림이 이미 사라졌으면 앱 첫 화면을 엽니다.
            }
        }
        if (e.pkg.equals(getPackageName())) return;
        Intent launch = getPackageManager().getLaunchIntentForPackage(e.pkg);
        if (launch != null) {
            startActivity(launch);
        } else {
            Toast.makeText(this, "이 앱을 열 수 없어요.", Toast.LENGTH_SHORT).show();
        }
    }

    /** 설치 후 소리·화면 깜빡임이 잘 되는지 확인하는 가짜 예약. 출처를 번갈아 넣습니다. */
    private void addTestEntry() {
        int src = testSource;
        testSource = (testSource + 1) % Config.SOURCES;
        long now = System.currentTimeMillis();
        Entry e = Store.get(this).insert(now, src, getPackageName(),
                "[테스트] 홍길동님 예약",
                "오늘 19:00 · 4명\n테스트 알림이에요. (" + timeFormat.format(new Date(now)) + ")");
        if (e == null) return;
        Alerter.get(this).alert(src);
        onEntry(e);
    }

    private long startOfToday() {
        Calendar cal = Calendar.getInstance();
        cal.set(Calendar.HOUR_OF_DAY, 0);
        cal.set(Calendar.MINUTE, 0);
        cal.set(Calendar.SECOND, 0);
        cal.set(Calendar.MILLISECOND, 0);
        return cal.getTimeInMillis();
    }

    private String timeLabel(long posted) {
        long start = startOfToday();
        Date d = new Date(posted);
        if (posted >= start) return timeFormat.format(d);
        if (posted >= start - 24L * 60 * 60 * 1000) return "어제 " + timeFormat.format(d);
        return dateTimeFormat.format(d);
    }

    // ---- 레이아웃 ----

    private View buildLayout() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Ui.BG);

        LinearLayout column = new LinearLayout(this);
        column.setOrientation(LinearLayout.VERTICAL);
        int pad = Ui.dp(this, 16);
        column.setPadding(pad, pad, pad, 0);
        root.addView(column, new FrameLayout.LayoutParams(-1, -1));
        Ui.fitSystemBars(column);

        // 맨 위: 제목, 수신 상태, 시계
        LinearLayout header = new LinearLayout(this);
        header.setGravity(Gravity.CENTER_VERTICAL);
        header.addView(Ui.text(this, "예약 알림판", 26, Ui.TEXT, true));
        status = Ui.text(this, "", 16, Ui.SUB, true);
        status.setPadding(Ui.dp(this, 14), 0, 0, 0);
        header.addView(status);
        header.addView(new View(this), new LinearLayout.LayoutParams(0, 1, 1f));
        clock = Ui.text(this, "", 24, Ui.TEXT, true);
        header.addView(clock);
        column.addView(header);

        banner = Ui.text(this, "", 18, Ui.TEXT, true);
        banner.setBackground(Ui.round(this, Ui.WARN, 14));
        banner.setPadding(pad, pad, pad, pad);
        banner.setVisibility(View.GONE);
        LinearLayout.LayoutParams bannerLp = new LinearLayout.LayoutParams(-1, -2);
        bannerLp.topMargin = Ui.dp(this, 12);
        column.addView(banner, bannerLp);

        // 출처별 탭(오늘 건수)과 버튼
        LinearLayout bar = new LinearLayout(this);
        bar.setGravity(Gravity.CENTER_VERTICAL);
        bar.addView(Ui.text(this, "오늘", 16, Ui.SUB, true));
        for (int i = 0; i < tabs.length; i++) {
            final int source = i - 1;
            TextView tab = Ui.button(this, "", Ui.CHIP);
            tab.setMinHeight(Ui.dp(this, 48));
            tab.setOnClickListener(v -> {
                filter = source;
                refresh();
            });
            LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-2, -2);
            lp.leftMargin = Ui.dp(this, 10);
            bar.addView(tab, lp);
            tabs[i] = tab;
        }
        bar.addView(new View(this), new LinearLayout.LayoutParams(Ui.dp(this, 24), 1));
        ack = Ui.button(this, "", 0xFFB45309);
        ack.setOnClickListener(v -> {
            Store.get(this).markAllSeen();
            refresh();
        });
        bar.addView(ack);
        TextView test = Ui.button(this, "테스트", Ui.CHIP);
        test.setOnClickListener(v -> addTestEntry());
        LinearLayout.LayoutParams testLp = new LinearLayout.LayoutParams(-2, -2);
        testLp.leftMargin = Ui.dp(this, 10);
        bar.addView(test, testLp);
        TextView settings = Ui.button(this, "설정", Ui.CHIP);
        settings.setOnClickListener(v -> startActivity(new Intent(this, SettingsActivity.class)));
        LinearLayout.LayoutParams settingsLp = new LinearLayout.LayoutParams(-2, -2);
        settingsLp.leftMargin = Ui.dp(this, 10);
        bar.addView(settings, settingsLp);

        HorizontalScrollView barScroll = new HorizontalScrollView(this);
        barScroll.setHorizontalScrollBarEnabled(false);
        barScroll.addView(bar);
        LinearLayout.LayoutParams barLp = new LinearLayout.LayoutParams(-1, -2);
        barLp.topMargin = Ui.dp(this, 12);
        barLp.bottomMargin = Ui.dp(this, 4);
        column.addView(barScroll, barLp);

        // 예약 목록
        FrameLayout listArea = new FrameLayout(this);
        list = new ListView(this);
        list.setDivider(null);
        list.setSelector(android.R.color.transparent);
        list.setClipToPadding(false);
        list.setPadding(0, 0, 0, pad);
        adapter = new EntryAdapter();
        list.setAdapter(adapter);
        list.setOnItemClickListener((parent, view, position, id) -> open(items.get(position)));
        listArea.addView(list, new FrameLayout.LayoutParams(-1, -1));
        empty = Ui.text(this, "아직 들어온 예약 알림이 없어요.\n새 예약이 오면 소리와 함께 여기에 나타나요.", 20, Ui.SUB, false);
        empty.setGravity(Gravity.CENTER);
        listArea.addView(empty, new FrameLayout.LayoutParams(-1, -1));
        column.addView(listArea, new LinearLayout.LayoutParams(-1, 0, 1f));

        // 새 예약이 오면 화면 전체를 출처 색으로 깜빡입니다. 터치는 막지 않아요.
        flash = new View(this);
        flash.setVisibility(View.GONE);
        root.addView(flash, new FrameLayout.LayoutParams(-1, -1));
        return root;
    }

    private final class EntryAdapter extends BaseAdapter {
        private final class Holder {
            LinearLayout card;
            View bar;
            TextView badge, time, fresh, title, body;
        }

        @Override
        public int getCount() {
            return items.size();
        }

        @Override
        public Object getItem(int position) {
            return items.get(position);
        }

        @Override
        public long getItemId(int position) {
            return items.get(position).id;
        }

        @Override
        public View getView(int position, View convertView, ViewGroup parent) {
            Holder h;
            if (convertView == null) {
                h = new Holder();
                FrameLayout wrap = new FrameLayout(MainActivity.this);
                wrap.setPadding(0, Ui.dp(MainActivity.this, 6), 0, Ui.dp(MainActivity.this, 6));

                h.card = new LinearLayout(MainActivity.this);
                h.card.setOrientation(LinearLayout.HORIZONTAL);
                wrap.addView(h.card, new FrameLayout.LayoutParams(-1, -2));

                h.bar = new View(MainActivity.this);
                h.card.addView(h.bar, new LinearLayout.LayoutParams(Ui.dp(MainActivity.this, 8), -1));

                LinearLayout content = new LinearLayout(MainActivity.this);
                content.setOrientation(LinearLayout.VERTICAL);
                int p = Ui.dp(MainActivity.this, 16);
                content.setPadding(p, p, p, p);
                h.card.addView(content, new LinearLayout.LayoutParams(0, -2, 1f));

                LinearLayout top = new LinearLayout(MainActivity.this);
                top.setGravity(Gravity.CENTER_VERTICAL);
                h.badge = Ui.text(MainActivity.this, "", 16, Ui.TEXT, true);
                h.badge.setPadding(Ui.dp(MainActivity.this, 12), Ui.dp(MainActivity.this, 4),
                        Ui.dp(MainActivity.this, 12), Ui.dp(MainActivity.this, 4));
                top.addView(h.badge);
                h.time = Ui.text(MainActivity.this, "", 18, Ui.SUB, true);
                h.time.setPadding(Ui.dp(MainActivity.this, 12), 0, 0, 0);
                top.addView(h.time);
                top.addView(new View(MainActivity.this), new LinearLayout.LayoutParams(0, 1, 1f));
                h.fresh = Ui.text(MainActivity.this, "NEW", 16, Ui.BG, true);
                h.fresh.setBackground(Ui.round(MainActivity.this, Ui.NEW, 8));
                h.fresh.setPadding(Ui.dp(MainActivity.this, 10), Ui.dp(MainActivity.this, 3),
                        Ui.dp(MainActivity.this, 10), Ui.dp(MainActivity.this, 3));
                top.addView(h.fresh);
                content.addView(top);

                h.title = Ui.text(MainActivity.this, "", 24, Ui.TEXT, true);
                h.title.setPadding(0, Ui.dp(MainActivity.this, 10), 0, 0);
                content.addView(h.title);
                h.body = Ui.text(MainActivity.this, "", 20, 0xFFD5DBE3, false);
                h.body.setPadding(0, Ui.dp(MainActivity.this, 6), 0, 0);
                h.body.setLineSpacing(0, 1.15f);
                content.addView(h.body);

                convertView = wrap;
                convertView.setTag(h);
            } else {
                h = (Holder) convertView.getTag();
            }

            Entry e = items.get(position);
            int color = Config.COLORS[e.source];
            h.card.setBackground(Ui.round(MainActivity.this, e.isNew ? Ui.CARD_NEW : Ui.CARD, 14));
            h.card.setClipToOutline(true);
            h.bar.setBackgroundColor(color);
            h.badge.setText(Config.name(MainActivity.this, e.source));
            h.badge.setBackground(Ui.round(MainActivity.this, color, 8));
            h.time.setText(timeLabel(e.posted) + " 수신");
            h.fresh.setVisibility(e.isNew ? View.VISIBLE : View.GONE);
            h.title.setText(e.title);
            h.title.setVisibility(e.title.isEmpty() ? View.GONE : View.VISIBLE);
            h.body.setText(e.body);
            h.body.setVisibility(e.body.isEmpty() ? View.GONE : View.VISIBLE);

            h.badge.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16 * scale);
            h.time.setTextSize(TypedValue.COMPLEX_UNIT_SP, 18 * scale);
            h.fresh.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16 * scale);
            h.title.setTextSize(TypedValue.COMPLEX_UNIT_SP, 24 * scale);
            h.body.setTextSize(TypedValue.COMPLEX_UNIT_SP, 20 * scale);
            return convertView;
        }
    }
}
