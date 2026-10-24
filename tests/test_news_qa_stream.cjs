const assert = require('assert').strict;
const {createParser} = require('../app/static/js/news-qa.js');
const events = [];
const parser = createParser(event => events.push(event));
const wire = 'data: {"type":"sources","sources":[]}\r\n\r\ndata: {"type":"content","content":"新闻正文"}\n\ndata: {"type":"done"}\n\ndata: [DONE]\n\n';
// Exercise every boundary, including the middle of Chinese strings and CRLF frames.
for (const char of wire) parser.push(char);
parser.finish();
assert.deepEqual(events.map(e=>e.type), ['sources','content','done']);
assert.equal(events[1].content, '新闻正文');
const final = [];
const tail = createParser(e=>final.push(e));
tail.push('data: {"type":"content","content":"末帧"}');
tail.finish();
assert.equal(final[0].content,'末帧');
console.log('PASS: incremental SSE decoding and final frame');
