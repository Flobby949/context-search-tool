package com.example.order;

final class OverloadService {
    void dispatch(Order order) {}

    void dispatch(OrderDto dto) {}
}
