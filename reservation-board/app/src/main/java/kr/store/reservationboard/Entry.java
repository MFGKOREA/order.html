package kr.store.reservationboard;

/** 알림판에 한 줄로 표시되는 예약 알림. */
final class Entry {
    final long id;
    final long posted;
    final int source;
    final String pkg;
    final String title;
    final String body;
    final boolean isNew;

    Entry(long id, long posted, int source, String pkg, String title, String body, boolean isNew) {
        this.id = id;
        this.posted = posted;
        this.source = source;
        this.pkg = pkg;
        this.title = title;
        this.body = body;
        this.isNew = isNew;
    }
}
