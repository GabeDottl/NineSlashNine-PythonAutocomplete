from . import command_router

def test_command_router():
  router = command_router.CommandRouter()
  source = '1'
  fix_input = {
    'request_id': 0, 
    'action': 'fix_code',
    'source': source,
    'filename': __file__
  }
  handler = router.get_handler('fix_code')
  result = handler(**fix_input)
  assert result[command_router.RESULT_CODE] == command_router.SUCCESS

if __name__ == "__main__":
  test_command_router()