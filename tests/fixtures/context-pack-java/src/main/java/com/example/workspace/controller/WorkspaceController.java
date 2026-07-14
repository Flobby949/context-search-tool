package com.example.workspace.controller;

import com.example.workspace.dto.WorkspaceDto;
import com.example.workspace.service.impl.WorkspaceServiceImpl;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/workspace")
public class WorkspaceController {
    private final WorkspaceServiceImpl workspaceService;

    public WorkspaceController(WorkspaceServiceImpl workspaceService) {
        this.workspaceService = workspaceService;
    }

    @GetMapping("/page")
    public WorkspaceDto page() {
        return workspaceService.page();
    }
}
