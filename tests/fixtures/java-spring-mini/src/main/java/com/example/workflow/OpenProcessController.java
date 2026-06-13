package com.example.workflow;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/open/process")
public class OpenProcessController {
    private final OpenProcessGateway openProcessGateway;

    public OpenProcessController(OpenProcessGateway openProcessGateway) {
        this.openProcessGateway = openProcessGateway;
    }

    /** apaas工作流相关接口 */
    @PostMapping("/start")
    public OpenProcessResponseDTO start(@RequestBody OpenProcessRequestDTO command) {
        return openProcessGateway.start(command);
    }

    /** apaas工作流相关接口 */
    @GetMapping("/list")
    public OpenProcessResponseDTO list() {
        return openProcessGateway.list();
    }
}

interface OpenProcessGateway {
    OpenProcessResponseDTO start(OpenProcessRequestDTO command);

    OpenProcessResponseDTO list();
}

class OpenProcessGatewayImpl implements OpenProcessGateway {
    @Override
    public OpenProcessResponseDTO start(OpenProcessRequestDTO command) {
        return new OpenProcessResponseDTO();
    }

    @Override
    public OpenProcessResponseDTO list() {
        return new OpenProcessResponseDTO();
    }
}

class OpenProcessRequestDTO {
}

class OpenProcessResponseDTO {
}

class OpenProcessCommand {
}
