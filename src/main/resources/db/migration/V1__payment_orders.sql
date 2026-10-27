CREATE TABLE payment_orders (
    id UUID PRIMARY KEY,
    merchant_id VARCHAR(40) NOT NULL,
    idempotency_key VARCHAR(64) NOT NULL,
    amount_paise BIGINT NOT NULL,
    currency VARCHAR(3) NOT NULL,
    status VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_merchant_idempotency UNIQUE (merchant_id, idempotency_key),
    CONSTRAINT ck_amount CHECK (amount_paise > 0 AND amount_paise <= 100000000),
    CONSTRAINT ck_currency CHECK (currency = 'INR'),
    CONSTRAINT ck_status CHECK (status IN ('CREATED', 'SUCCESS', 'FAILED', 'REFUNDED'))
);
