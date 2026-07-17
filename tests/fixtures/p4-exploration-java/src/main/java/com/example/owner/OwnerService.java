package com.example.owner;

import org.springframework.stereotype.Service;

@Service
public class OwnerService {
    public void save(Owner owner) {
        owner.setId(1L);
    }
}
