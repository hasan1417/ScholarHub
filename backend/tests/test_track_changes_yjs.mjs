/**
 * test_track_changes_yjs.mjs
 *
 * Pure Y.js tests for the track-changes logic from useTrackChanges.ts.
 * No React, no CodeMirror -- only yjs primitives.
 *
 * Run:  node backend/tests/test_track_changes_yjs.mjs
 */

const Y = await import(
  '/Users/hassan/Desktop/Coding/MX/Final Project/ScholarHub/frontend/node_modules/yjs/dist/yjs.mjs'
)

// -- Helpers (ported from useTrackChanges.ts) ------------------------------

function parseTrackMeta(raw) {
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

function changeId(type, pos, userId, timestamp) {
  return `${type}-${pos}-${userId}-${timestamp}`
}

function collectTrackedChanges(yText) {
  const delta = yText.toDelta()
  const changes = []
  let pos = 0

  for (const op of delta) {
    if (typeof op.insert === 'string') {
      const len = op.insert.length
      const attrs = op.attributes || {}

      const insertMeta = parseTrackMeta(attrs.trackInsert)
      if (insertMeta) {
        changes.push({
          id: changeId('insert', pos, insertMeta.userId, insertMeta.timestamp),
          type: 'insert',
          position: pos,
          length: len,
          text: op.insert,
          userId: insertMeta.userId,
          userName: insertMeta.userName,
          userColor: insertMeta.userColor,
          timestamp: insertMeta.timestamp,
        })
      }

      const deleteMeta = parseTrackMeta(attrs.trackDelete)
      if (deleteMeta) {
        changes.push({
          id: changeId('delete', pos, deleteMeta.userId, deleteMeta.timestamp),
          type: 'delete',
          position: pos,
          length: len,
          text: op.insert,
          userId: deleteMeta.userId,
          userName: deleteMeta.userName,
          userColor: deleteMeta.userColor,
          timestamp: deleteMeta.timestamp,
        })
      }

      pos += len
    }
  }

  return changes
}

// -- Test infrastructure ---------------------------------------------------

let passed = 0
let failed = 0
const failures = []

function assert(condition, message) {
  if (!condition) throw new Error('Assertion failed: ' + message)
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(
      message + '\n  expected: ' + JSON.stringify(expected) + '\n  actual:   ' + JSON.stringify(actual)
    )
  }
}

function assertDeepEqual(actual, expected, message) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a !== e) {
    throw new Error(message + '\n  expected: ' + e + '\n  actual:   ' + a)
  }
}

function test(name, fn) {
  try {
    fn()
    console.log('  PASS  ' + name)
    passed++
  } catch (err) {
    console.log('  FAIL  ' + name)
    console.log('        ' + err.message.split('\n').join('\n        '))
    failed++
    failures.push(name)
  }
}

// -- Tests -----------------------------------------------------------------

console.log('')
console.log('=== Y.js Track Changes Unit Tests ===')
console.log('')

// 1. collectTrackedChanges on clean text returns empty
test('collectTrackedChanges returns [] for plain text', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'hello world')
  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 0, 'should be empty')
})

// 2. collectTrackedChanges finds trackInsert
test('collectTrackedChanges finds trackInsert attribute', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'hello world')

  const meta = JSON.stringify({
    userId: 'user-1',
    userName: 'Alice',
    userColor: '#ff0000',
    timestamp: 1000,
  })
  yText.format(6, 5, { trackInsert: meta })

  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 1, 'should find one change')
  assertEqual(changes[0].type, 'insert', 'type should be insert')
  assertEqual(changes[0].position, 6, 'position should be 6')
  assertEqual(changes[0].length, 5, 'length should be 5')
  assertEqual(changes[0].text, 'world', 'text should be "world"')
  assertEqual(changes[0].userId, 'user-1', 'userId')
  assertEqual(changes[0].userName, 'Alice', 'userName')
})

// 3. collectTrackedChanges finds trackDelete
test('collectTrackedChanges finds trackDelete attribute', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'hello world')

  const meta = JSON.stringify({
    userId: 'user-2',
    userName: 'Bob',
    timestamp: 2000,
  })
  yText.format(0, 5, { trackDelete: meta })

  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 1, 'should find one change')
  assertEqual(changes[0].type, 'delete', 'type should be delete')
  assertEqual(changes[0].text, 'hello', 'text should be "hello"')
  assertEqual(changes[0].userId, 'user-2', 'userId')
})

// 4. collectTrackedChanges finds both insert and delete together
test('collectTrackedChanges finds both insert and delete in same text', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'ABCDE')

  const insertMeta = JSON.stringify({ userId: 'u1', userName: 'Alice', timestamp: 100 })
  const deleteMeta = JSON.stringify({ userId: 'u2', userName: 'Bob', timestamp: 200 })

  yText.format(0, 2, { trackInsert: insertMeta })
  yText.format(3, 2, { trackDelete: deleteMeta })

  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 2, 'should find two changes')
  assertEqual(changes[0].type, 'insert', 'first is insert')
  assertEqual(changes[0].text, 'AB', 'insert text')
  assertEqual(changes[1].type, 'delete', 'second is delete')
  assertEqual(changes[1].text, 'DE', 'delete text')
})

// 5. Observer marks local insertion with trackInsert
test('observer marks local insertion with trackInsert attribute', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')

  let enabledRef = true
  let applyingTrackRef = false
  const userRef = { userId: 'user-1', userName: 'Alice', userColor: '#00f' }

  const observer = (event, transaction) => {
    if (!enabledRef) return
    if (applyingTrackRef) return
    if (!transaction.local) return

    let pos = 0
    for (const delta of event.delta) {
      if (delta.retain != null) {
        pos += delta.retain
      } else if (delta.insert != null) {
        const text = typeof delta.insert === 'string' ? delta.insert : ''
        const len = text.length
        if (len > 0) {
          const attrs = delta.attributes || {}
          if (!attrs.trackInsert) {
            const meta = JSON.stringify({
              userId: userRef.userId,
              userName: userRef.userName,
              userColor: userRef.userColor,
              timestamp: 9999,
            })
            applyingTrackRef = true
            try {
              yText.format(pos, len, { trackInsert: meta })
            } finally {
              applyingTrackRef = false
            }
          }
        }
        pos += len
      }
    }
  }

  yText.observe(observer)

  doc.transact(() => {
    yText.insert(0, 'hello')
  })

  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 1, 'one tracked change')
  assertEqual(changes[0].type, 'insert', 'type is insert')
  assertEqual(changes[0].text, 'hello', 'text is hello')
  assertEqual(changes[0].userId, 'user-1', 'userId matches')

  yText.unobserve(observer)
})

// 6. Observer transaction.local is true for local transact
test('transaction.local is true for doc.transact()', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  let observedLocal = null

  const observer = (_event, transaction) => {
    observedLocal = transaction.local
  }
  yText.observe(observer)

  doc.transact(() => {
    yText.insert(0, 'test')
  })

  assertEqual(observedLocal, true, 'transaction.local should be true')
  yText.unobserve(observer)
})

// 7. Observer transaction.local is false for remote changes
test('transaction.local is false for remote apply', () => {
  const doc1 = new Y.Doc()
  doc1.clientID = 1
  const doc2 = new Y.Doc()
  doc2.clientID = 2

  const yText2 = doc2.getText('test')
  let observedLocal = null

  const observer = (_event, transaction) => {
    observedLocal = transaction.local
  }
  yText2.observe(observer)

  const yText1 = doc1.getText('test')
  yText1.insert(0, 'remote text')

  const stateVector2 = Y.encodeStateVector(doc2)
  const update = Y.encodeStateAsUpdate(doc1, stateVector2)
  Y.applyUpdate(doc2, update)

  assertEqual(observedLocal, false, 'transaction.local should be false for remote updates')
  yText2.unobserve(observer)
})

// 8. Observer does NOT mark remote insertions
test('observer skips remote insertions (transaction.local === false)', () => {
  const doc1 = new Y.Doc()
  doc1.clientID = 10
  const doc2 = new Y.Doc()
  doc2.clientID = 20

  const yText2 = doc2.getText('test')

  let enabledRef = true
  let applyingTrackRef = false

  const observer = (event, transaction) => {
    if (!enabledRef) return
    if (applyingTrackRef) return
    if (!transaction.local) return

    let pos = 0
    for (const delta of event.delta) {
      if (delta.retain != null) {
        pos += delta.retain
      } else if (delta.insert != null) {
        const text = typeof delta.insert === 'string' ? delta.insert : ''
        const len = text.length
        if (len > 0) {
          const attrs = delta.attributes || {}
          if (!attrs.trackInsert) {
            applyingTrackRef = true
            try {
              yText2.format(pos, len, {
                trackInsert: JSON.stringify({ userId: 'local', userName: 'Local', timestamp: 1 }),
              })
            } finally {
              applyingTrackRef = false
            }
          }
        }
        pos += len
      }
    }
  }

  yText2.observe(observer)

  const yText1 = doc1.getText('test')
  yText1.insert(0, 'from remote')
  const sv = Y.encodeStateVector(doc2)
  const update = Y.encodeStateAsUpdate(doc1, sv)
  Y.applyUpdate(doc2, update)

  const changes = collectTrackedChanges(yText2)
  assertEqual(changes.length, 0, 'no tracked changes for remote insertions')
  yText2.unobserve(observer)
})

// 9. Observer skips insertions that already have trackInsert
test('observer skips insertion that already has trackInsert attribute', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')

  let formatCallCount = 0
  let enabledRef = true
  let applyingTrackRef = false

  const observer = (event, transaction) => {
    if (!enabledRef) return
    if (applyingTrackRef) return
    if (!transaction.local) return

    let pos = 0
    for (const delta of event.delta) {
      if (delta.retain != null) {
        pos += delta.retain
      } else if (delta.insert != null) {
        const text = typeof delta.insert === 'string' ? delta.insert : ''
        const len = text.length
        if (len > 0) {
          const attrs = delta.attributes || {}
          if (!attrs.trackInsert) {
            formatCallCount++
            applyingTrackRef = true
            try {
              yText.format(pos, len, {
                trackInsert: JSON.stringify({ userId: 'u', userName: 'U', timestamp: 1 }),
              })
            } finally {
              applyingTrackRef = false
            }
          }
        }
        pos += len
      }
    }
  }

  yText.observe(observer)

  doc.transact(() => {
    yText.insert(0, 'pre-marked', {
      trackInsert: JSON.stringify({ userId: 'other', userName: 'Other', timestamp: 500 }),
    })
  })

  assertEqual(formatCallCount, 0, 'format should NOT be called for pre-attributed insertion')

  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 1, 'one change exists')
  assertEqual(changes[0].userId, 'other', 'userId from original attribute preserved')

  yText.unobserve(observer)
})

// 10. Observer is disabled when enabledRef = false
test('observer does nothing when track changes is disabled', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')

  let enabledRef = false
  let applyingTrackRef = false
  let formatCalled = false

  const observer = (event, transaction) => {
    if (!enabledRef) return
    if (applyingTrackRef) return
    if (!transaction.local) return

    formatCalled = true
  }

  yText.observe(observer)
  doc.transact(() => { yText.insert(0, 'should not track') })

  assertEqual(formatCalled, false, 'observer should not format when disabled')
  assertEqual(collectTrackedChanges(yText).length, 0, 'no tracked changes')
  yText.unobserve(observer)
})

// 11. Deletion marking via format (transaction filter logic)
test('marking text with trackDelete via format()', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'delete me please')

  const meta = JSON.stringify({
    userId: 'user-1',
    userName: 'Alice',
    timestamp: 3000,
  })

  yText.format(7, 2, { trackDelete: meta })

  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 1, 'one delete change')
  assertEqual(changes[0].type, 'delete', 'type is delete')
  assertEqual(changes[0].text, 'me', 'deleted text is "me"')
  assertEqual(changes[0].position, 7, 'position is 7')

  const fullText = yText.toString()
  assertEqual(fullText, 'delete me please', 'text should remain in document')
})

// 12. Accept tracked insert (remove trackInsert attr)
test('accept insert: removes trackInsert, text stays', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'hello world')

  const meta = JSON.stringify({ userId: 'u1', userName: 'A', timestamp: 100 })
  yText.format(6, 5, { trackInsert: meta })

  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 1, 'one change before accept')

  yText.format(changes[0].position, changes[0].length, { trackInsert: null })

  const afterChanges = collectTrackedChanges(yText)
  assertEqual(afterChanges.length, 0, 'no changes after accept')
  assertEqual(yText.toString(), 'hello world', 'text unchanged')
})

// 13. Accept tracked delete (actually delete the text)
test('accept delete: removes text from document', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'hello world')

  const meta = JSON.stringify({ userId: 'u1', userName: 'A', timestamp: 100 })
  yText.format(5, 6, { trackDelete: meta })

  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 1, 'one change before accept')
  assertEqual(changes[0].type, 'delete', 'is a delete')

  yText.delete(changes[0].position, changes[0].length)

  assertEqual(yText.toString(), 'hello', 'text after accepting delete')
  assertEqual(collectTrackedChanges(yText).length, 0, 'no changes remain')
})

// 14. Reject tracked insert (delete the text)
test('reject insert: deletes the inserted text', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'hello world')

  const meta = JSON.stringify({ userId: 'u1', userName: 'A', timestamp: 100 })
  yText.format(6, 5, { trackInsert: meta })

  const changes = collectTrackedChanges(yText)
  yText.delete(changes[0].position, changes[0].length)

  assertEqual(yText.toString(), 'hello ', 'text after rejecting insert')
  assertEqual(collectTrackedChanges(yText).length, 0, 'no changes remain')
})

// 15. Reject tracked delete (remove trackDelete attr, text reappears)
test('reject delete: removes trackDelete attribute, text stays', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'hello world')

  const meta = JSON.stringify({ userId: 'u1', userName: 'A', timestamp: 100 })
  yText.format(0, 5, { trackDelete: meta })

  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 1, 'one change')

  yText.format(changes[0].position, changes[0].length, { trackDelete: null })

  assertEqual(collectTrackedChanges(yText).length, 0, 'no changes after reject')
  assertEqual(yText.toString(), 'hello world', 'text unchanged')
})

// 16. Accept all changes (inserts + deletes, reverse order)
test('acceptAll processes changes in reverse order correctly', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'AB_old_CD_new_EF')

  const delMeta = JSON.stringify({ userId: 'u1', userName: 'A', timestamp: 1 })
  const insMeta = JSON.stringify({ userId: 'u1', userName: 'A', timestamp: 2 })

  yText.format(2, 5, { trackDelete: delMeta })
  yText.format(9, 5, { trackInsert: insMeta })

  let changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 2, 'two changes before acceptAll')

  changes.sort((a, b) => b.position - a.position)
  for (const change of changes) {
    if (change.type === 'insert') {
      yText.format(change.position, change.length, { trackInsert: null })
    } else {
      yText.delete(change.position, change.length)
    }
  }

  assertEqual(collectTrackedChanges(yText).length, 0, 'no changes remain')
  assertEqual(yText.toString(), 'ABCD_new_EF', 'correct final text')
})

// 17. Reject all changes (inserts + deletes, reverse order)
test('rejectAll processes changes in reverse order correctly', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'AB_old_CD_new_EF')

  const delMeta = JSON.stringify({ userId: 'u1', userName: 'A', timestamp: 1 })
  const insMeta = JSON.stringify({ userId: 'u1', userName: 'A', timestamp: 2 })

  yText.format(2, 5, { trackDelete: delMeta })
  yText.format(9, 5, { trackInsert: insMeta })

  let changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 2, 'two changes')

  changes.sort((a, b) => b.position - a.position)
  for (const change of changes) {
    if (change.type === 'insert') {
      yText.delete(change.position, change.length)
    } else {
      yText.format(change.position, change.length, { trackDelete: null })
    }
  }

  assertEqual(collectTrackedChanges(yText).length, 0, 'no changes remain')
  assertEqual(yText.toString(), 'AB_old_CDEF', 'correct final text')
})

// 18. format() inside observer does not throw
test('yText.format() inside observer callback does not throw', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  let formatSucceeded = false
  let formatError = null

  const observer = (event, transaction) => {
    if (!transaction.local) return
    let pos = 0
    for (const delta of event.delta) {
      if (delta.retain != null) {
        pos += delta.retain
      } else if (delta.insert != null) {
        const text = typeof delta.insert === 'string' ? delta.insert : ''
        if (text.length > 0) {
          try {
            yText.format(pos, text.length, {
              trackInsert: JSON.stringify({ userId: 'x', userName: 'X', timestamp: 0 }),
            })
            formatSucceeded = true
          } catch (err) {
            formatError = err
          }
        }
        pos += text.length
      }
    }
  }

  yText.observe(observer)
  doc.transact(() => { yText.insert(0, 'abc') })

  assertEqual(formatError, null, 'no error thrown')
  assertEqual(formatSucceeded, true, 'format was called successfully')

  yText.unobserve(observer)
})

// 19. toDelta() shows trackInsert attribute after format in observer
test('toDelta() reflects trackInsert attribute after observer formats', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')

  const observer = (event, transaction) => {
    if (!transaction.local) return
    let pos = 0
    for (const delta of event.delta) {
      if (delta.retain != null) pos += delta.retain
      else if (delta.insert != null) {
        const text = typeof delta.insert === 'string' ? delta.insert : ''
        if (text.length > 0 && !(delta.attributes || {}).trackInsert) {
          yText.format(pos, text.length, {
            trackInsert: JSON.stringify({ userId: 'obs', userName: 'Obs', timestamp: 42 }),
          })
        }
        pos += text.length
      }
    }
  }

  yText.observe(observer)
  doc.transact(() => { yText.insert(0, 'xyz') })
  yText.unobserve(observer)

  const delta = yText.toDelta()
  assertEqual(delta.length, 1, 'single delta op')
  assertEqual(delta[0].insert, 'xyz', 'insert text')
  assert(delta[0].attributes != null, 'attributes should exist')
  const meta = parseTrackMeta(delta[0].attributes.trackInsert)
  assert(meta != null, 'trackInsert meta should be parseable')
  assertEqual(meta.userId, 'obs', 'userId in meta')
  assertEqual(meta.timestamp, 42, 'timestamp in meta')
})

// 20. Adjacent sequential insertions merge attributes (Y.js behaviour)
//     When you insert at the boundary of already-attributed text, Y.js
//     inherits the attributes from the neighbour.  The observer correctly
//     skips re-formatting because trackInsert is already present.  Result:
//     one merged tracked change, not three.
test('adjacent sequential insertions merge into one tracked change', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  let applyingTrackRef = false
  let callCount = 0

  const observer = (event, transaction) => {
    if (applyingTrackRef) return
    if (!transaction.local) return

    let pos = 0
    for (const delta of event.delta) {
      if (delta.retain != null) pos += delta.retain
      else if (delta.insert != null) {
        const text = typeof delta.insert === 'string' ? delta.insert : ''
        if (text.length > 0 && !(delta.attributes || {}).trackInsert) {
          callCount++
          applyingTrackRef = true
          try {
            yText.format(pos, text.length, {
              trackInsert: JSON.stringify({
                userId: 'u',
                userName: 'U',
                timestamp: callCount * 1000,
              }),
            })
          } finally {
            applyingTrackRef = false
          }
        }
        pos += text.length
      }
    }
  }

  yText.observe(observer)

  doc.transact(() => { yText.insert(0, 'AAA') })
  doc.transact(() => { yText.insert(3, 'BBB') })
  doc.transact(() => { yText.insert(6, 'CCC') })

  yText.unobserve(observer)

  // Y.js merges adjacent text with identical attributes into one delta op.
  // Only the first insert triggers format(); the next two inherit the attr.
  assertEqual(callCount, 1, 'format called only once (first insert)')
  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 1, 'one merged tracked change')
  assertEqual(changes[0].text, 'AAABBBCCC', 'all text merged')
  assertEqual(changes[0].timestamp, 1000, 'timestamp from first insert')
})

// 20b. Non-adjacent insertions produce separate tracked changes
test('non-adjacent insertions produce separate tracked changes', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  // Start with plain untracked text as separators
  yText.insert(0, '...')

  let applyingTrackRef = false
  let callCount = 0

  const observer = (event, transaction) => {
    if (applyingTrackRef) return
    if (!transaction.local) return

    let pos = 0
    for (const delta of event.delta) {
      if (delta.retain != null) pos += delta.retain
      else if (delta.insert != null) {
        const text = typeof delta.insert === 'string' ? delta.insert : ''
        if (text.length > 0 && !(delta.attributes || {}).trackInsert) {
          callCount++
          applyingTrackRef = true
          try {
            yText.format(pos, text.length, {
              trackInsert: JSON.stringify({
                userId: 'u',
                userName: 'U',
                timestamp: callCount * 1000,
              }),
            })
          } finally {
            applyingTrackRef = false
          }
        }
        pos += text.length
      }
    }
  }

  yText.observe(observer)

  // Insert at position 0 (before the plain '...')
  doc.transact(() => { yText.insert(0, 'AA') })
  // Insert at position 5 (after 'AA...' = 5 chars, so after the untracked gap)
  doc.transact(() => { yText.insert(5, 'BB') })

  yText.unobserve(observer)

  assertEqual(callCount, 2, 'format called twice (non-adjacent inserts)')
  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 2, 'two separate tracked changes')
  assertEqual(changes[0].text, 'AA', 'first change text')
  assertEqual(changes[1].text, 'BB', 'second change text')
})

// 21. parseTrackMeta handles edge cases
test('parseTrackMeta handles null/undefined/invalid JSON', () => {
  assertEqual(parseTrackMeta(null), null, 'null input')
  assertEqual(parseTrackMeta(undefined), null, 'undefined input')
  assertEqual(parseTrackMeta(''), null, 'empty string')
  assertEqual(parseTrackMeta('not json'), null, 'invalid JSON')
  const valid = parseTrackMeta(JSON.stringify({ userId: 'a', userName: 'b', timestamp: 1 }))
  assertEqual(valid.userId, 'a', 'valid JSON parses')
})

// 22. Text with both trackInsert AND trackDelete on same range
test('same range can have both trackInsert and trackDelete', () => {
  const doc = new Y.Doc()
  const yText = doc.getText('test')
  yText.insert(0, 'overlap')

  const insertMeta = JSON.stringify({ userId: 'u1', userName: 'A', timestamp: 1 })
  const deleteMeta = JSON.stringify({ userId: 'u2', userName: 'B', timestamp: 2 })

  yText.format(0, 7, { trackInsert: insertMeta })
  yText.format(0, 7, { trackDelete: deleteMeta })

  const changes = collectTrackedChanges(yText)
  assertEqual(changes.length, 2, 'both changes detected')

  const types = changes.map(c => c.type).sort()
  assertDeepEqual(types, ['delete', 'insert'], 'one insert and one delete')
})

// -- Summary ---------------------------------------------------------------

console.log('')
console.log('-'.repeat(50))
console.log('Results: ' + passed + ' passed, ' + failed + ' failed, ' + (passed + failed) + ' total')
if (failures.length > 0) {
  console.log('')
  console.log('Failed tests:')
  for (const f of failures) {
    console.log('  - ' + f)
  }
}
console.log('')

process.exit(failed > 0 ? 1 : 0)
