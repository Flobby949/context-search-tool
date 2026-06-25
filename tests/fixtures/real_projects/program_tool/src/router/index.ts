import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    {
      path: '/ai-chat',
      name: 'ai-chat',
      component: () => import('../views/ai/AiChat.vue'),
      meta: { title: 'AI chat assistant' },
    },
    {
      path: '/json-to-entity',
      name: 'json-to-entity',
      component: () => import('../views/json/JsonToEntity.vue'),
      meta: { title: 'JSON to entity generator' },
    },
    {
      path: '/qrcode-tool',
      name: 'qrcode-tool',
      component: () => import('../views/qrcode/QRCodeTool.vue'),
      meta: { title: 'QRCode generate and scan tool' },
    },
    {
      path: '/mqtt-tool',
      name: 'mqtt-tool',
      component: () => import('../views/communication/MqttTool.vue'),
      meta: { title: 'MQTT websocket test tool' },
    },
    {
      path: '/watermark-remover',
      name: 'watermark-remover',
      component: () => import('../views/image/WatermarkRemover.vue'),
      meta: { title: 'Watermark remover' },
    },
  ],
})

export default router
