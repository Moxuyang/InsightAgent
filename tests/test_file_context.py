from pathlib import Path
import sqlite3,tempfile,json,unittest
from contextlib import contextmanager
from unittest.mock import patch
from app.services import file_context as f

class FileContextTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);(self.root/'uploads').mkdir()
  self.db=self.root/'test.db'
  self.patches=[patch.object(f,'ROOT',self.root),patch.object(f,'UPLOAD_ROOT',self.root/'uploads'),patch.object(f,'get_connection',self.connection)]
  for p in self.patches:p.start()
  with self.connection() as c:
   c.executescript('CREATE TABLE user_files(id INTEGER PRIMARY KEY,user_id INTEGER,file_name TEXT,file_path TEXT,file_type TEXT,create_at TEXT);CREATE TABLE chat_sessions(id INTEGER PRIMARY KEY,user_id INTEGER,is_active INTEGER);INSERT INTO chat_sessions VALUES(1,1,1);')
 def tearDown(self):
  for p in self.patches:p.stop()
  self.temp.cleanup()
 @contextmanager
 def connection(self):
  c=sqlite3.connect(self.db);c.row_factory=sqlite3.Row
  try:yield c;c.commit()
  finally:c.close()
 def record(self,text='来源,篇数,字数\n百度,2,120\n头条,3,180\n'):
  (self.root/'uploads/test.csv').write_text(text,encoding='utf-8-sig')
  with self.connection() as c:c.execute("INSERT OR REPLACE INTO user_files VALUES(1,1,'test.csv','uploads/test.csv','csv','2026-10-22')")
  return {'file_path':'uploads/test.csv','file_type':'csv'}
 def test_totals_are_computed_from_real_cells(self):
  result=json.loads(f.read_document(self.record()))
  self.assertEqual(result['row_count'],2)
  self.assertEqual(result['numeric_statistics_all_rows']['篇数']['sum'],'5')
  self.assertEqual(result['numeric_statistics_all_rows']['字数']['sum'],'300')
 def test_other_user_cannot_read_file_or_session(self):
  self.record()
  with self.assertRaises(PermissionError):f.load_attachments(2,0,[1])
  with self.assertRaises(PermissionError):f.load_attachments(2,1,[])
 def test_bound_file_remains_after_followup(self):
  self.record();sources=f.load_attachments(1,1,[1]);f.bind_attachments(1,sources)
  self.assertEqual(f.load_attachments(1,1,[])[0]['title'],'test.csv')
 def test_path_escape_and_duplicate_headers_are_rejected(self):
  (self.root/'outside.csv').write_text('a\n1')
  with self.assertRaises(ValueError):f.read_document({'file_path':'outside.csv','file_type':'csv'})
  with self.assertRaises(ValueError):f.read_document(self.record('a,a\n1,2'))
 def test_malformed_csv_and_unsupported_type(self):
  with self.assertRaises(ValueError):f.read_document(self.record('a,b\n1'))
  record=self.record();record['file_type']='xlsx'
  with self.assertRaises(ValueError):f.read_document(record)

if __name__=='__main__':unittest.main()
