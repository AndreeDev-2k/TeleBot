
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

COMMIT;
