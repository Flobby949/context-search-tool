package com.example.catalog;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/appCatalog")
public class AppCatalogController {
    private final AppInfoService appInfoService;

    public AppCatalogController(AppInfoService appInfoService) {
        this.appInfoService = appInfoService;
    }

    @PostMapping("/page")
    public String page(@RequestBody AppCatalogPageQry qry) {
        return appInfoService.page(qry);
    }
}
