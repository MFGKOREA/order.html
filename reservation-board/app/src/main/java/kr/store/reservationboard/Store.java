package kr.store.reservationboard;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.util.ArrayList;
import java.util.List;

/** 받은 예약 알림 기록. 태블릿 안에만 저장됩니다. */
final class Store extends SQLiteOpenHelper {
    /** 같은 내용의 알림이 다시 올라와도(알림 갱신 등) 이 시간 안이면 한 번만 기록합니다. */
    private static final long DEDUP_WINDOW = 24L * 60 * 60 * 1000;

    private static Store instance;

    static synchronized Store get(Context c) {
        if (instance == null) instance = new Store(c.getApplicationContext());
        return instance;
    }

    private Store(Context c) {
        super(c, "board.db", null, 1);
    }

    @Override
    public void onCreate(SQLiteDatabase db) {
        db.execSQL("CREATE TABLE entries ("
                + "id INTEGER PRIMARY KEY AUTOINCREMENT,"
                + "posted INTEGER NOT NULL,"
                + "source INTEGER NOT NULL,"
                + "pkg TEXT NOT NULL,"
                + "title TEXT NOT NULL,"
                + "body TEXT NOT NULL,"
                + "is_new INTEGER NOT NULL DEFAULT 1)");
        db.execSQL("CREATE INDEX entries_posted ON entries(posted)");
    }

    @Override
    public void onUpgrade(SQLiteDatabase db, int oldVersion, int newVersion) {
    }

    /** 새로 기록했으면 그 항목을, 이미 있는 알림이면 null을 돌려줍니다. */
    synchronized Entry insert(long posted, int source, String pkg, String title, String body) {
        SQLiteDatabase db = getWritableDatabase();
        try (Cursor c = db.rawQuery(
                "SELECT 1 FROM entries WHERE pkg=? AND title=? AND body=? AND posted BETWEEN ? AND ? LIMIT 1",
                new String[]{pkg, title, body,
                        String.valueOf(posted - DEDUP_WINDOW), String.valueOf(posted + DEDUP_WINDOW)})) {
            if (c.moveToFirst()) return null;
        }
        ContentValues v = new ContentValues();
        v.put("posted", posted);
        v.put("source", source);
        v.put("pkg", pkg);
        v.put("title", title);
        v.put("body", body);
        v.put("is_new", 1);
        long id = db.insert("entries", null, v);
        return id < 0 ? null : new Entry(id, posted, source, pkg, title, body, true);
    }

    /** since 이후 항목, 최신순. source가 -1이면 전체. */
    synchronized List<Entry> recent(long since, int source) {
        List<Entry> out = new ArrayList<>();
        String where = "posted>=?" + (source >= 0 ? " AND source=?" : "");
        String[] args = source >= 0
                ? new String[]{String.valueOf(since), String.valueOf(source)}
                : new String[]{String.valueOf(since)};
        try (Cursor c = getReadableDatabase().query("entries",
                new String[]{"id", "posted", "source", "pkg", "title", "body", "is_new"},
                where, args, null, null, "posted DESC", "300")) {
            while (c.moveToNext()) {
                out.add(new Entry(c.getLong(0), c.getLong(1), c.getInt(2),
                        c.getString(3), c.getString(4), c.getString(5), c.getInt(6) != 0));
            }
        }
        return out;
    }

    synchronized int[] countsSince(long since) {
        int[] counts = new int[Config.SOURCES];
        try (Cursor c = getReadableDatabase().rawQuery(
                "SELECT source, COUNT(*) FROM entries WHERE posted>=? GROUP BY source",
                new String[]{String.valueOf(since)})) {
            while (c.moveToNext()) {
                int src = c.getInt(0);
                if (src >= 0 && src < counts.length) counts[src] = c.getInt(1);
            }
        }
        return counts;
    }

    synchronized int newCount() {
        try (Cursor c = getReadableDatabase().rawQuery("SELECT COUNT(*) FROM entries WHERE is_new=1", null)) {
            return c.moveToFirst() ? c.getInt(0) : 0;
        }
    }

    synchronized void markSeen(long id) {
        ContentValues v = new ContentValues();
        v.put("is_new", 0);
        getWritableDatabase().update("entries", v, "id=?", new String[]{String.valueOf(id)});
    }

    synchronized void markAllSeen() {
        ContentValues v = new ContentValues();
        v.put("is_new", 0);
        getWritableDatabase().update("entries", v, "is_new=1", null);
    }

    synchronized void purgeBefore(long time) {
        getWritableDatabase().delete("entries", "posted<?", new String[]{String.valueOf(time)});
    }

    synchronized void clear() {
        getWritableDatabase().delete("entries", null, null);
    }
}
