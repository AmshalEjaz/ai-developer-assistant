import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';

const appJsx = fs.readFileSync(new URL('./src/App.jsx', import.meta.url), 'utf8');
const appCss = fs.readFileSync(new URL('./src/App.css', import.meta.url), 'utf8');

test('dark attach button is transparent with a white plus', () => {
  assert.match(
    appCss,
    /\.app\[data-theme="dark"\]\s+\.attach\s*\{[^}]*background:\s*transparent;[^}]*color:\s*(?:#fff|white);/s,
  );
});

test('composer auto-grows and hides its visible scrollbar', () => {
  assert.match(appJsx, /composerTextareaRef/);
  assert.match(appJsx, /resizeComposerTextarea/);
  assert.match(appCss, /\.composer textarea::\-webkit-scrollbar\s*\{[^}]*display:\s*none;/s);
  assert.match(appCss, /\.composer textarea\s*\{[^}]*max-height:\s*220px;/s);
});

test('assistant markdown uses normal whitespace and compact spacing', () => {
  assert.match(
    appCss,
    /\.assistant-message\s+\.message-text\s*\{[^}]*white-space:\s*normal;/s,
  );
  assert.match(appCss, /\.chat-message\s*\{[^}]*margin-bottom:\s*18px;/s);
  assert.match(appCss, /\.message-text p\s*\{[^}]*margin:\s*0 0 5px;/s);
});

test('conversation history exposes delete menu and confirmation dialog', () => {
  assert.match(appJsx, /conversation-menu-button/);
  assert.match(appJsx, /deleteConversation/);
  assert.match(appJsx, /delete-confirm-overlay/);
});

test('user messages render on the right side', () => {
  assert.match(appCss, /\.user-message\s*\{[^}]*flex-direction:\s*row-reverse;/s);
  assert.match(appCss, /\.user-message\s+\.message-content\s*\{[^}]*align-items:\s*flex-end;/s);
});

test('long user messages can expand and collapse', () => {
  assert.match(appJsx, /function\s+UserMessageContent/);
  assert.match(appJsx, /Show more/);
  assert.match(appJsx, /Show less/);
  assert.match(appCss, /\.user-message-body\.collapsed\s*\{[^}]*max-height:/s);
});

test('fenced code blocks show language and copy control', () => {
  assert.match(appJsx, /function\s+CodeBlock/);
  assert.match(appJsx, /code-block-header/);
  assert.match(appJsx, /navigator\.clipboard\.writeText/);
  assert.match(appJsx, /components=\{\{\s*pre:\s*CodeBlock\s*\}\}/s);
  assert.match(appCss, /\.code-copy-button/);
});

test('message spacing stays compact', () => {
  assert.match(appCss, /\.message-text\s*\{[^}]*padding:\s*8px 11px;/s);
  assert.match(appCss, /\.message-text p\s*\{[^}]*margin:\s*0 0 4px;/s);
  assert.match(appCss, /\.message-text pre\s*\{[^}]*margin:\s*0;/s);
});
