package com.learning.payments;

import jakarta.persistence.*;
import java.time.Instant;
import java.util.UUID;

@Entity
@Table(name = "payment_orders")
public class PaymentOrder {
    public enum Status { CREATED, SUCCESS, FAILED, REFUNDED }

    @Id @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;
    @Column(nullable = false, length = 40)
    private String merchantId;
    @Column(nullable = false, length = 64)
    private String idempotencyKey;
    @Column(nullable = false)
    private long amountPaise;
    @Column(nullable = false, length = 3)
    private String currency;
    @Enumerated(EnumType.STRING) @Column(nullable = false, length = 16)
    private Status status;
    @Column(nullable = false)
    private Instant createdAt;

    protected PaymentOrder() {}

    PaymentOrder(String merchantId, String idempotencyKey, long amountPaise, String currency) {
        this.merchantId = merchantId;
        this.idempotencyKey = idempotencyKey;
        this.amountPaise = amountPaise;
        this.currency = currency;
        this.status = Status.CREATED;
        this.createdAt = Instant.now();
    }

    public UUID getId() { return id; }
    public String getMerchantId() { return merchantId; }
    public long getAmountPaise() { return amountPaise; }
    public String getCurrency() { return currency; }
    public Status getStatus() { return status; }
    public Instant getCreatedAt() { return createdAt; }
    void setStatus(Status status) { this.status = status; }
}
