package com.example.audit;

import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/apply/audit")
public class ResourceApplyAuditController {
    private final ResourceAuditService resourceAuditService;

    public ResourceApplyAuditController(ResourceAuditService resourceAuditService) {
        this.resourceAuditService = resourceAuditService;
    }

    @PostMapping("/pageEs")
    public String applyPageEs() {
        return resourceAuditService.applyPageEs(AuditStatus.INVOLVED_BY_ME);
    }
}
