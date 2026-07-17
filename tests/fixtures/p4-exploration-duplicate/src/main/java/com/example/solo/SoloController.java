package com.example.solo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class SoloController {
    public static final String SOLO_VIEW = "solo/index";

    @GetMapping("/solo")
    public String showSolo() {
        return SOLO_VIEW;
    }
}
