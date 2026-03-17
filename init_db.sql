
BEGIN;

-- 1. Bảng groups: lưu các chat_id mà bot đã join
CREATE TABLE IF NOT EXISTS groups (
    id          SERIAL PRIMARY KEY,
    chat_id     BIGINT    NOT NULL UNIQUE,
    chat_title  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at   TIMESTAMPTZ
);

-- 2. Bảng shops: lưu thông tin shop_name và shop_id
CREATE TABLE IF NOT EXISTS shops (
    shop_name TEXT PRIMARY KEY,
    shop_id   BIGINT NOT NULL UNIQUE
);

-- 3. Bảng seen_ids: đánh dấu các listing đã gửi, tránh trùng lặp
CREATE TABLE IF NOT EXISTS seen_ids (
    shop_name   TEXT    NOT NULL REFERENCES shops(shop_name) ON DELETE CASCADE,
    listing_id  TEXT    NOT NULL,
    seen_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (shop_name, listing_id)
);

-- 4. Bảng group_subscriptions: mapping giữa chat_id và shop
CREATE TABLE IF NOT EXISTS group_subscriptions (
    id            SERIAL PRIMARY KEY,
    chat_id       BIGINT  NOT NULL REFERENCES groups(chat_id) ON DELETE CASCADE,
    shop_name     TEXT    NOT NULL REFERENCES shops(shop_name) ON DELETE CASCADE,
    shop_id       BIGINT  NOT NULL REFERENCES shops(shop_id) ON DELETE CASCADE,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    deleted_at    TIMESTAMPTZ
);

-- 5. Indexes để tối ưu truy vấn
CREATE INDEX IF NOT EXISTS idx_seen_ids_shop ON seen_ids(shop_name);
CREATE INDEX IF NOT EXISTS idx_subscriptions_chat ON group_subscriptions(chat_id);

-- ── FACEBOOK FANPAGE ─────────────────────────────────────────────────────────

    -- 6. Bảng fb_pages: lưu các Facebook page đang theo dõi
    CREATE TABLE IF NOT EXISTS fb_pages (
        page_id   TEXT PRIMARY KEY,
        page_name TEXT NOT NULL
    );

    -- 7. Bảng fb_group_subscriptions: mapping giữa group và Facebook page
    CREATE TABLE IF NOT EXISTS fb_group_subscriptions (
        chat_id   BIGINT NOT NULL REFERENCES groups(chat_id) ON DELETE CASCADE,
        page_id   TEXT   NOT NULL REFERENCES fb_pages(page_id) ON DELETE CASCADE,
        PRIMARY KEY (chat_id, page_id)
    );

    -- 8. Bảng fb_seen_posts: đánh dấu bài đã gửi, tránh gửi lại
    CREATE TABLE IF NOT EXISTS fb_seen_posts (
        page_id TEXT NOT NULL,
        post_id TEXT NOT NULL,
        seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (page_id, post_id)
    );

    CREATE INDEX IF NOT EXISTS idx_fb_seen_page ON fb_seen_posts(page_id);

-- 9. Bảng fb_posts: lưu đầy đủ nội dung bài đăng Facebook
CREATE TABLE IF NOT EXISTS fb_posts (
    page_id         TEXT        NOT NULL,
    post_id         TEXT        NOT NULL,
    page_name       TEXT        NOT NULL,
    created_at      TIMESTAMPTZ,
    message         TEXT,
    image_url       TEXT,
    post_url        TEXT,
    reaction_count  INTEGER     NOT NULL DEFAULT 0,
    comment_count   INTEGER     NOT NULL DEFAULT 0,
    fetched_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (page_id, post_id)
);

CREATE INDEX IF NOT EXISTS idx_fb_posts_page    ON fb_posts(page_id);
CREATE INDEX IF NOT EXISTS idx_fb_posts_created ON fb_posts(created_at DESC);

