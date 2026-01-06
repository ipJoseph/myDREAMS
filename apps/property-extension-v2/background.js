// background.js - Service Worker for myDREAMS Property Capture
// Handles extension lifecycle and potential API interception

console.log('myDREAMS Property Capture v2: Background service worker loaded');

// Extension installed or updated
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    console.log('Extension installed');
  } else if (details.reason === 'update') {
    console.log('Extension updated to version', chrome.runtime.getManifest().version);
  }
});

// Listen for messages from popup or content scripts
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'getVersion') {
    sendResponse({ version: chrome.runtime.getManifest().version });
  }
  return true;
});

// Future: API response interception could be added here using 
// chrome.webRequest if we move to more advanced data extraction
