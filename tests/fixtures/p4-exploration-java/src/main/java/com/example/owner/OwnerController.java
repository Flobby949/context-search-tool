package com.example.owner;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
public class OwnerController {
    public static final String VIEWS_OWNER_CREATE_OR_UPDATE_FORM =
            "owners/createOrUpdateOwnerForm";

    private final OwnerService ownerService;

    public OwnerController(OwnerService ownerService) {
        this.ownerService = ownerService;
    }

    @GetMapping("/owners/new")
    public String initCreationForm(Owner owner) {
        return VIEWS_OWNER_CREATE_OR_UPDATE_FORM;
    }

    @PostMapping("/owners/new")
    public String processCreationForm(Owner owner) {
        ownerService.save(owner);
        return "redirect:/owners/" + owner.getId();
    }
}
