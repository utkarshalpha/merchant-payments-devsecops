package com.learning.payments;

import tools.jackson.databind.cfg.CoercionAction;
import tools.jackson.databind.cfg.CoercionInputShape;
import tools.jackson.databind.type.LogicalType;
import org.springframework.boot.jackson.autoconfigure.JsonMapperBuilderCustomizer;
import org.springframework.context.annotation.*;

@Configuration
class JsonConfiguration {
    @Bean
    JsonMapperBuilderCustomizer strictIntegerAmounts() {
        return builder -> builder.withCoercionConfig(LogicalType.Integer, config -> config
            .setCoercion(CoercionInputShape.String, CoercionAction.Fail));
    }
}
