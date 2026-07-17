package com.example.order;

final class OverloadCaller {
    private final OverloadService service;

    OverloadCaller(OverloadService service) {
        this.service = service;
    }

    void invoke(Object value) {
        service.dispatch(value);
    }
}
