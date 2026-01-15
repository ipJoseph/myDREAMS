/**
 * DREAMS Property Scraper - Background Service Worker
 *
 * Manages:
 * - Server health checking
 * - Offline queue processing
 * - Message passing between content scripts and popup
 */

const CONFIG = {
  SERVER_URL: 'http://localhost:5000',
  HEALTH_CHECK_INTERVAL: 30000,
  RETRY_DELAYS: [1000, 5000, 15000, 60000, 300000],
  MAX_RETRIES: 5
};

// ============================================
// QUEUE MANAGER
// ============================================

class QueueManager {
  constructor() {
    this.processing = false;
  }

  async getQueue() {
    const { propertyQueue = [] } = await chrome.storage.local.get('propertyQueue');
    return propertyQueue;
  }

  async addToQueue(data, operation = 'create') {
    const item = {
      id: crypto.randomUUID(),
      timestamp: Date.now(),
      retryCount: 0,
      maxRetries: CONFIG.MAX_RETRIES,
      data,
      operation,
      status: 'pending'
    };

    const queue = await this.getQueue();
    queue.push(item);
    await chrome.storage.local.set({ propertyQueue: queue });

    // Try immediate send
    this.processQueue();

    return item.id;
  }

  async removeFromQueue(itemId) {
    const queue = await this.getQueue();
    const filtered = queue.filter(item => item.id !== itemId);
    await chrome.storage.local.set({ propertyQueue: filtered });
  }

  async updateQueueItem(itemId, updates) {
    const queue = await this.getQueue();
    const index = queue.findIndex(item => item.id === itemId);
    if (index >= 0) {
      queue[index] = { ...queue[index], ...updates };
      await chrome.storage.local.set({ propertyQueue: queue });
    }
  }

  async processQueue() {
    if (this.processing) return;
    this.processing = true;

    try {
      const status = await this.checkServerHealth();
      if (status !== 'online') {
        this.processing = false;
        return;
      }

      const queue = await this.getQueue();
      const pending = queue.filter(item => item.status === 'pending');

      for (const item of pending) {
        try {
          await this.sendToServer(item);
          await this.removeFromQueue(item.id);

          // Notify popup of success
          chrome.runtime.sendMessage({
            type: 'QUEUE_ITEM_PROCESSED',
            itemId: item.id,
            success: true
          }).catch(() => {});

        } catch (error) {
          await this.handleRetry(item, error);
        }
      }
    } finally {
      this.processing = false;
    }
  }

  async sendToServer(item) {
    const response = await fetch(`${CONFIG.SERVER_URL}/api/v1/properties`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify(item.data)
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error?.message || `HTTP ${response.status}`);
    }

    return await response.json();
  }

  async handleRetry(item, error) {
    const retryCount = item.retryCount + 1;

    if (retryCount >= item.maxRetries) {
      await this.updateQueueItem(item.id, {
        status: 'failed',
        error: error.message,
        retryCount
      });

      chrome.runtime.sendMessage({
        type: 'QUEUE_ITEM_FAILED',
        itemId: item.id,
        error: error.message
      }).catch(() => {});

    } else {
      const delay = CONFIG.RETRY_DELAYS[Math.min(retryCount - 1, CONFIG.RETRY_DELAYS.length - 1)];
      await this.updateQueueItem(item.id, { retryCount });

      // Schedule retry
      setTimeout(() => this.processQueue(), delay);
    }
  }

  async checkServerHealth() {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 5000);

      const response = await fetch(`${CONFIG.SERVER_URL}/health`, {
        method: 'GET',
        signal: controller.signal
      });

      clearTimeout(timeoutId);

      const status = response.ok ? 'online' : 'offline';
      await chrome.storage.local.set({ serverStatus: status });
      return status;

    } catch (error) {
      await chrome.storage.local.set({ serverStatus: 'offline' });
      return 'offline';
    }
  }
}

const queueManager = new QueueManager();

// ============================================
// MESSAGE HANDLERS
// ============================================

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  handleMessage(message, sender).then(sendResponse);
  return true; // Keep channel open for async response
});

async function handleMessage(message, sender) {
  switch (message.type) {
    case 'GET_SERVER_STATUS':
      return { status: await queueManager.checkServerHealth() };

    case 'GET_QUEUE':
      return { queue: await queueManager.getQueue() };

    case 'ADD_TO_QUEUE':
      const queueId = await queueManager.addToQueue(message.data, message.operation);
      return { success: true, queueId };

    case 'PROCESS_QUEUE':
      queueManager.processQueue();
      return { success: true };

    case 'SAVE_PROPERTY':
      return await saveProperty(message.data);

    case 'GET_PROPERTY_DATA':
      // Forward to content script
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab) {
        try {
          const response = await chrome.tabs.sendMessage(tab.id, { type: 'SCRAPE_PROPERTY' });
          return response;
        } catch (error) {
          return { error: 'Content script not loaded. Please refresh the page.' };
        }
      }
      return { error: 'No active tab' };

    case 'GET_SEARCH_RESULTS':
      const [searchTab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (searchTab) {
        try {
          const response = await chrome.tabs.sendMessage(searchTab.id, { type: 'SCRAPE_SEARCH' });
          return response;
        } catch (error) {
          return { error: 'Content script not loaded. Please refresh the page.' };
        }
      }
      return { error: 'No active tab' };

    case 'POP_OUT_WINDOW':
      // Store the active tab ID for the new window to use
      const [activeTab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (activeTab) {
        await chrome.storage.local.set({ popoutSourceTabId: activeTab.id });
      }
      // Open popup in a new window
      await chrome.windows.create({
        url: chrome.runtime.getURL('popup/index.html?popout=true'),
        type: 'popup',
        width: 560,
        height: 750,
        focused: true
      });
      return { success: true };

    default:
      return { error: 'Unknown message type' };
  }
}

async function saveProperty(data) {
  const serverStatus = await queueManager.checkServerHealth();

  if (serverStatus === 'online') {
    try {
      const response = await fetch(`${CONFIG.SERVER_URL}/api/v1/properties`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });

      const result = await response.json();
      if (result.success) {
        return { success: true, data: result.data, queued: false };
      } else {
        throw new Error(result.error?.message || 'Save failed');
      }
    } catch (error) {
      // Fall back to queue
      const queueId = await queueManager.addToQueue(data);
      return { success: true, queued: true, queueId };
    }
  } else {
    // Server offline, add to queue
    const queueId = await queueManager.addToQueue(data);
    return { success: true, queued: true, queueId };
  }
}

// ============================================
// PERIODIC HEALTH CHECK
// ============================================

setInterval(() => {
  queueManager.checkServerHealth().then(status => {
    if (status === 'online') {
      queueManager.processQueue();
    }
  });
}, CONFIG.HEALTH_CHECK_INTERVAL);

// Initial health check
queueManager.checkServerHealth();

console.log('DREAMS Property Scraper background service started');
