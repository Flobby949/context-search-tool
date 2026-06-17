package com.example.catalog;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/openApi/appCatalog")
public class AppCatalogOpenController {
    @PostMapping("/page")
    public String page() {
        return "open";
    }
}
