package com.learning.payments;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.UUID;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class PaymentService {
    public record Created(PaymentApi.OrderView order, boolean created) {}
    private final PaymentOrderRepository repository;
    private final TransactionTemplate transactions;
    private final Counter createdOrders;

    PaymentService(PaymentOrderRepository repository, PlatformTransactionManager manager,
                   MeterRegistry metrics) {
        this.repository = repository;
        this.transactions = new TransactionTemplate(manager);
        this.createdOrders = metrics.counter("merchant.payment.orders");
    }

    public Created create(PaymentApi.CreateOrder request, String key) {
        if (!key.matches("[a-zA-Z0-9_-]{8,64}")) {
            throw new ApiException(HttpStatus.BAD_REQUEST, "Idempotency-Key must be 8-64 letters, digits, underscores or hyphens");
        }
        Created result;
        try {
            result = transactions.execute(tx -> {
                var existing = repository.findByMerchantIdAndIdempotencyKey(request.merchantId(), key);
                if (existing.isPresent()) return replay(existing.get(), request);
                var order = repository.saveAndFlush(new PaymentOrder(request.merchantId(), key,
                    request.amountPaise(), request.currency()));
                return new Created(PaymentApi.OrderView.from(order), true);
            });
        } catch (DataIntegrityViolationException collision) {
            // A simultaneous retry can win the unique-key race. The failed transaction
            // has already rolled back before we read the winner in a fresh transaction.
            result = transactions.execute(tx -> repository
                .findByMerchantIdAndIdempotencyKey(request.merchantId(), key)
                .map(order -> replay(order, request)).orElseThrow(() -> collision));
        }
        if (result.created()) createdOrders.increment();
        return result;
    }

    private Created replay(PaymentOrder order, PaymentApi.CreateOrder request) {
        if (order.getAmountPaise() != request.amountPaise()
            || !order.getCurrency().equals(request.currency())) {
            throw new ApiException(HttpStatus.CONFLICT, "This idempotency key was already used with different payment details");
        }
        return new Created(PaymentApi.OrderView.from(order), false);
    }

    public PaymentApi.OrderView get(UUID id) {
        return repository.findById(id).map(PaymentApi.OrderView::from)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Payment order not found"));
    }

    public PaymentApi.OrderView simulate(UUID id, PaymentApi.Outcome outcome) {
        return transactions.execute(tx -> {
            var order = locked(id);
            var next = PaymentOrder.Status.valueOf(outcome.name());
            if (order.getStatus() != PaymentOrder.Status.CREATED && order.getStatus() != next) {
                throw new ApiException(HttpStatus.CONFLICT, "A completed payment outcome cannot be changed");
            }
            order.setStatus(next);
            return PaymentApi.OrderView.from(order);
        });
    }

    public PaymentApi.OrderView refund(UUID id) {
        return transactions.execute(tx -> {
            var order = locked(id);
            if (order.getStatus() != PaymentOrder.Status.SUCCESS
                && order.getStatus() != PaymentOrder.Status.REFUNDED) {
                throw new ApiException(HttpStatus.CONFLICT, "Only successful payments can be refunded");
            }
            order.setStatus(PaymentOrder.Status.REFUNDED);
            return PaymentApi.OrderView.from(order);
        });
    }

    private PaymentOrder locked(UUID id) {
        return repository.findLockedById(id)
            .orElseThrow(() -> new ApiException(HttpStatus.NOT_FOUND, "Payment order not found"));
    }
}
