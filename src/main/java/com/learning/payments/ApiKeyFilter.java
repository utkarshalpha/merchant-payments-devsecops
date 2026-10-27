package com.learning.payments;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
class ApiKeyFilter extends OncePerRequestFilter {
    private final byte[] expected;

    ApiKeyFilter(@Value("${payments.api-key}") String apiKey) {
        if (apiKey.length() < 32) {
            throw new IllegalArgumentException("Set PAYMENTS_API_KEY to a random value of at least 32 characters");
        }
        this.expected = apiKey.getBytes(StandardCharsets.UTF_8);
    }

    @Override
    protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                    FilterChain chain) throws ServletException, IOException {
        response.setHeader("X-Content-Type-Options", "nosniff");
        response.setHeader("Cache-Control", "no-store");
        if (request.getRequestURI().startsWith("/api/")) {
            String provided = request.getHeader("X-API-Key");
            if (provided == null || !MessageDigest.isEqual(expected,
                    provided.getBytes(StandardCharsets.UTF_8))) {
                response.setStatus(401);
                response.setContentType("application/json");
                response.getWriter().write("{\"error\":\"Invalid API key\"}");
                return;
            }
        }
        chain.doFilter(request, response);
    }
}
