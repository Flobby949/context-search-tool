package com.example.order;

final class OrderDto {
    private final long id;

    OrderDto(long id) {
        this.id = id;
    }

    long id() {
        return id;
    }
}
