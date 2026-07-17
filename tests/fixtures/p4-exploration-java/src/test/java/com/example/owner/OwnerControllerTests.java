package com.example.owner;

import org.junit.jupiter.api.Test;

class OwnerControllerTests {
    @Test
    void validatesOwnerRegistrationForm() {
        Owner owner = new Owner();
        owner.setFirstName("Jane");
        owner.setLastName("Doe");
    }
}
