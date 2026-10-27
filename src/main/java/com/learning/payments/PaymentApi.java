package com.learning.payments;

import jakarta.validation.Valid;
import jakarta.validation.constraints.*;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/payment-orders")
public class PaymentApi {
    public record CreateOrder(
        @NotBlank @Pattern(regexp = "[a-zA-Z0-9_-]{1,40}") String merchantId,
        @NotNull @Min(1) @Max(100_000_000) Long amountPaise,
        @NotBlank @Pattern(regexp = "INR") String currency
    ) {}
    public enum Outcome { SUCCESS, FAILED }
    public record Simulate(@NotNull Outcome outcome) {}
    public record OrderView(UUID id, String merchantId, long amountPaise, String currency,
                            PaymentOrder.Status status, Instant createdAt, boolean simulated) {
        static OrderView from(PaymentOrder order) {
            return new OrderView(order.getId(), order.getMerchantId(), order.getAmountPaise(),
                order.getCurrency(), order.getStatus(), order.getCreatedAt(), true);
        }
    }

    private final PaymentService service;
    PaymentApi(PaymentService service) { this.service = service; }

    @PostMapping
    public ResponseEntity<OrderView> create(@RequestHeader("Idempotency-Key") String key,
                                            @Valid @RequestBody CreateOrder request) {
        var result = service.create(request, key);
        return ResponseEntity.status(result.created() ? 201 : 200).body(result.order());
    }

    @GetMapping("/{id}")
    public OrderView get(@PathVariable UUID id) { return service.get(id); }

    @PostMapping("/{id}/simulate")
    public OrderView simulate(@PathVariable UUID id, @Valid @RequestBody Simulate request) {
        return service.simulate(id, request.outcome());
    }

    @PostMapping("/{id}/refund")
    public OrderView refund(@PathVariable UUID id) { return service.refund(id); }
}
