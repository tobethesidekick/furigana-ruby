import http.server, os
os.chdir('/Users/yi-hsuanwu/Documents/ClaudeProjects/furigana-ruby/mockup')
http.server.test(HandlerClass=http.server.SimpleHTTPRequestHandler, port=7788, bind='127.0.0.1')
