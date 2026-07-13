package com.example.dashboard;

public final class DashboardController {
    private final StatisticsService statisticsService;

    public DashboardController(StatisticsService statisticsService) {
        this.statisticsService = statisticsService;
    }

    public String dashboard() {
        return statisticsService.statistics();
    }
}
