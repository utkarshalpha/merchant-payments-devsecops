FROM eclipse-temurin:21-jre-alpine@sha256:b48e02e0ea88d7bfb305335df94923bdef394905f4147dccd52e873cf17b1088
# Patched Alpine package for CVE-2026-111497; keep the container gate strict.
RUN apk add --no-cache --upgrade 'brotli-libs=1.2.1-r0'
WORKDIR /app
COPY target/merchant-payments.jar /app/app.jar
ENV SERVER_ADDRESS=0.0.0.0 SERVER_PORT=8081
USER 10001:10001
EXPOSE 8081
ENTRYPOINT ["java", "-XX:MaxRAMPercentage=60", "-XX:+ExitOnOutOfMemoryError", "-jar", "/app/app.jar"]
