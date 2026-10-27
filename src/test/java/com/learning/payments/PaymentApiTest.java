package com.learning.payments;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import io.micrometer.core.instrument.MeterRegistry;
import java.util.List;
import java.util.concurrent.*;
import org.junit.jupiter.api.*;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.webmvc.test.autoconfigure.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.*;
import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest(properties = {
    "payments.api-key=unit-test-only-key-not-a-real-secret-12345",
    "spring.datasource.url=jdbc:h2:mem:payments-tests;DB_CLOSE_DELAY=-1"
})
@AutoConfigureMockMvc
class PaymentApiTest {
    private static final String KEY = "unit-test-only-key-not-a-real-secret-12345";
    private static final String BODY = """
        {"merchantId":"demo-merchant","amountPaise":10000,"currency":"INR"}
        """;
    @Autowired MockMvc http;
    @Autowired ObjectMapper json;
    @Autowired PaymentOrderRepository repository;
    @Autowired MeterRegistry metrics;

    @BeforeEach void clearOrders() { repository.deleteAll(); }

    private ResultActions create(String key, String body) throws Exception {
        return http.perform(post("/api/payment-orders").header("X-API-Key", KEY)
            .header("Idempotency-Key", key).contentType(MediaType.APPLICATION_JSON).content(body));
    }

    private String newOrderId() throws Exception {
        return json.readTree(create("order-key-001", BODY).andExpect(status().isCreated())
            .andReturn().getResponse().getContentAsString()).get("id").asText();
    }

    @Test void createAndReadOrder() throws Exception {
        String id = newOrderId();
        http.perform(get("/api/payment-orders/" + id).header("X-API-Key", KEY))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("CREATED"))
            .andExpect(jsonPath("$.amountPaise").value(10000))
            .andExpect(jsonPath("$.simulated").value(true));
    }

    @Test void aRetryReturnsTheSameOrder() throws Exception {
        double before = metrics.counter("merchant.payment.orders").count();
        String id = newOrderId();
        create("order-key-001", BODY).andExpect(status().isOk())
            .andExpect(jsonPath("$.id").value(id));
        assertThat(repository.count()).isEqualTo(1);
        assertThat(metrics.counter("merchant.payment.orders").count()).isEqualTo(before + 1);
    }

    @Test void sameKeyWithDifferentDetailsIsRejected() throws Exception {
        newOrderId();
        create("order-key-001", BODY.replace("10000", "20000"))
            .andExpect(status().isConflict());
        assertThat(repository.count()).isEqualTo(1);
    }

    @Test void identicalKeysForDifferentMerchantsAreIndependent() throws Exception {
        newOrderId();
        create("order-key-001", BODY.replace("demo-merchant", "another-merchant"))
            .andExpect(status().isCreated());
        assertThat(repository.count()).isEqualTo(2);
    }

    @Test void simultaneousRetriesCreateOnlyOneOrder() throws Exception {
        var start = new CountDownLatch(1);
        try (var pool = Executors.newFixedThreadPool(2)) {
            Callable<MvcResult> request = () -> {
                start.await();
                return create("parallel-key-001", BODY).andReturn();
            };
            var first = pool.submit(request);
            var second = pool.submit(request);
            start.countDown();
            var a = first.get(20, TimeUnit.SECONDS).getResponse();
            var b = second.get(20, TimeUnit.SECONDS).getResponse();
            assertThat(List.of(a.getStatus(), b.getStatus())).containsExactlyInAnyOrder(200, 201);
            assertThat(json.readTree(a.getContentAsString()).get("id"))
                .isEqualTo(json.readTree(b.getContentAsString()).get("id"));
        }
        assertThat(repository.count()).isEqualTo(1);
    }

    @Test void successfulPaymentCanBeRefundedAndRefundRetriesAreSafe() throws Exception {
        String id = newOrderId();
        http.perform(post("/api/payment-orders/" + id + "/simulate").header("X-API-Key", KEY)
            .contentType(MediaType.APPLICATION_JSON).content("{\"outcome\":\"SUCCESS\"}"))
            .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("SUCCESS"));
        for (int i = 0; i < 2; i++) {
            http.perform(post("/api/payment-orders/" + id + "/refund").header("X-API-Key", KEY))
                .andExpect(status().isOk()).andExpect(jsonPath("$.status").value("REFUNDED"));
        }
    }

    @Test void createdOrderCannotBeRefunded() throws Exception {
        String id = newOrderId();
        http.perform(post("/api/payment-orders/" + id + "/refund").header("X-API-Key", KEY))
            .andExpect(status().isConflict());
    }

    @Test void failedOrderCannotBecomeSuccessfulOrRefunded() throws Exception {
        String id = newOrderId();
        http.perform(post("/api/payment-orders/" + id + "/simulate").header("X-API-Key", KEY)
            .contentType(MediaType.APPLICATION_JSON).content("{\"outcome\":\"FAILED\"}"))
            .andExpect(status().isOk());
        http.perform(post("/api/payment-orders/" + id + "/simulate").header("X-API-Key", KEY)
            .contentType(MediaType.APPLICATION_JSON).content("{\"outcome\":\"SUCCESS\"}"))
            .andExpect(status().isConflict());
        http.perform(post("/api/payment-orders/" + id + "/refund").header("X-API-Key", KEY))
            .andExpect(status().isConflict());
    }

    @ParameterizedTest
    @ValueSource(strings = {"0", "-1", "100000001", "1.5", "true", "\"10000\"", "null"})
    void invalidAmountsAreRejected(String amount) throws Exception {
        create("invalid-amount-key", BODY.replace("10000", amount))
            .andExpect(status().isBadRequest());
        assertThat(repository.count()).isZero();
    }

    @Test void unsupportedCurrencyAndUnknownFieldsAreRejected() throws Exception {
        create("invalid-currency-key", BODY.replace("INR", "USD"))
            .andExpect(status().isBadRequest());
        create("unknown-field-key", BODY.replace("10000,", "10000,\"status\":\"SUCCESS\","))
            .andExpect(status().isBadRequest());
    }

    @Test void invalidIdempotencyKeyIsRejected() throws Exception {
        create("short", BODY).andExpect(status().isBadRequest());
    }

    @Test void apiRequiresAKeyButHealthIsPublic() throws Exception {
        http.perform(post("/api/payment-orders").header("Idempotency-Key", "unauth-key-001")
            .contentType(MediaType.APPLICATION_JSON).content(BODY))
            .andExpect(status().isUnauthorized());
        http.perform(get("/api/payment-orders/00000000-0000-0000-0000-000000000000")
            .header("X-API-Key", "incorrect"))
            .andExpect(status().isUnauthorized());
        http.perform(get("/actuator/health")).andExpect(status().isOk());
    }

    @Test void unknownOrderReturns404() throws Exception {
        http.perform(get("/api/payment-orders/00000000-0000-0000-0000-000000000000")
            .header("X-API-Key", KEY)).andExpect(status().isNotFound());
    }
}
