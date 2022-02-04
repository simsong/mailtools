ROSETTE=False

if ROSETTE:
    import rosette
    from rosette.api import API,DocumentParameters, RosetteException
    with open("rosette.txt","r") as f:
        api = API(user_key=f.read().strip())
else:
    import extract_proper_nouns


if ROSETTE:
    params = DocumentParameters()
    params["content"] = text
    try:
        res = api.entities(params)
    except rosette.api.RosetteException:
        return
    for entity in res['entities']:
        print(f"{entity['type']} {entity['normalized']}  ('{entity['mention']}')")
