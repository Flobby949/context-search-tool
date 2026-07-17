package com.example.order;

final class Order {
    private final long id;

    Order(long id) {
        this.id = id;
    }

    long id() {
        return id;
    }
}
