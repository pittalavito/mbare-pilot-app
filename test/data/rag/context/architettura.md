# Architettura

Il negozio è un monolite modulare in Java 21 con Spring Boot.

## Backend
Il backend espone API REST sotto /api/v1. I moduli sono catalogo, carrello, ordini e pagamenti.
Ogni modulo ha il suo package e non chiama le classi interne degli altri: parla con le loro facade.

## Database
PostgreSQL 16, uno schema per modulo. Le migrazioni sono con Flyway nella cartella db/migration.
Le tabelle degli ordini sono partizionate per mese.

## Code e messaggi
Gli eventi tra moduli passano da RabbitMQ: OrderPlaced, PaymentCaptured, StockReserved.
Un consumer che fallisce tre volte manda il messaggio nella dead letter queue orders.dlq.
