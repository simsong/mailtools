import bottle
import os

STATIC_DIR = os.path.join( os.path.dirname(__file__), 'static' )

@bottle.route('/')
def home():
    bottle.redirect("/static/index.html")

# % https://stackoverflow.com/questions/10486224/bottle-static-files
@bottle.route('/static/<filepath:path>')
def server_static(filepath):
    return bottle.static_file(filepath, root = STATIC_DIR)

if __name__=="__main__":
    app = bottle.default_app()
    bottle.run(host='0.0.0.0', port=8000, server='paste')
    

