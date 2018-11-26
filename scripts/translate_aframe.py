# 2018-08-10 nembery@paloaltonetworks.com
#
# Simple script to take an AFrame screen as an argument
# find all input_form labels and translate them to another language using google translate APIs
#
# Example:
#
# find ~/PycharmProjects/panos-bootstrapper-ui/aframe/imports/screens/ |
#   sed 's/.*/"&"/' |
#       xargs -n 1 -I{} python ./translate_aframe.py {} it
#

import json
import os
import pickle
import uuid
from urllib.parse import quote, unquote

from googletrans import Translator

cache_file_path = '/tmp/translation_cache.pkl'
output_dir = '/tmp/translator_output'

translator = ''


def load_translation_cache(cache_file):
    """
    Open the cache file from the given path
    :param cache_file: Path to the cache
    :return: Dict containing all translated strings
    """

    if not os.path.exists(cache_file):
        with open(cache_file, 'wb+') as cache:
            pickle.dump({}, cache)
            return {}

    with open(cache_file, 'rb') as cache:
        trans_cache = pickle.load(cache)

    return trans_cache


def save_translation_cache(cache_file, cache):
    """
    Saves the translation cache into a pickle file
    :param cache_file: path to file to pickle
    :param cache: data structure to save
    :return: boolean on success
    """
    try:
        with open(cache_file, 'wb') as cache_obj:
            pickle.dump(cache, cache_obj)
    except OSError as oe:
        print(f'Could not open {cache_file} for writing!')
        return False

    return True


def get_screen_data_from_file(file_name):
    """
    Opens the screen file from the given path and return the contained data structure
    :param file_name: full path to an exported AFrame screen.json file
    :return: data structure from the file
    """
    screen_data = dict()

    try:
        with open(file_name, 'r') as file_obj:
            file_string = file_obj.read()
            screen_data = json.loads(file_string)
    except OSError as oe:
        print(f'Error opening {file_name}')
        print(oe)
        os.sys.exit(1)
    except ValueError as ve:
        print(f'Error ready json data in {file_name}')
        os.sys.exit(1)

    return screen_data


def is_english(screen_data):
    """
    Verifies there is a label with name=='language' and value=='english'
    :param screen_data:
    :return: boolean
    """
    label_data = screen_data.get('labels', [])
    screen_info = screen_data.get('screen', {})
    screen_name = screen_info.get('name', '')

    is_english = False
    for label in label_data:
        print(label)
        if label.get('name', '') == 'language' and label.get('value', '') == 'english':
            is_english = True
            break
        elif label.get('name', '') == 'language' and label.get('value', '') == 'en':
            is_english = True
            break

    if not is_english:
        print(f'This screen {screen_name} does not contain an english language label')
        return False

    return True


def set_lang_label(label_data, lang):
    """
    Changes the language label to be the correct language after translation
    :param label_data: label_data sructure from the screen file json
    :param lang: language code of the destination language
    :return: modified label data
    """
    for label in label_data:
        if label.get('name', '') == 'language' and label.get('value', '') == 'english':
            label['value'] = lang
            break
        elif label.get('name', '') == 'language' and label.get('value', '') == 'en':
            label['value'] = lang
            break

    return label_data


def process_screen(orig_screen_data, lang, cache, translate_form_names=True):
    """
    Process the screen data to translate all input_form labels
    :param orig_screen_data: screen data structure
    :param lang: destination language
    :param cache: translation cache to check
    :param translate_form_names: Translate form names as well as labels?
    :return: new screen data structure with input_forms translated
    """
    translated_screen = orig_screen_data
    form_data = translated_screen.get('input_forms', {})
    label_data = orig_screen_data.get('labels', [])

    translated_screen['labels'] = set_lang_label(label_data, lang)

    # OK, we can open the file, parse the data and have actually found it to be english. Let's translate all the form
    # labels in all the input_forms

    new_form_data = {}

    for input_form_id in form_data:
        input_form = form_data[input_form_id]
        input_form_obj = json.loads(input_form)
        form = input_form_obj.get('form', '')
        form_json = form.get('json', '')
        if form_json != '':
            form_json_unq = unquote(form_json, encoding='utf-8')
            form_vars = json.loads(form_json_unq)

            new_form = form
            if translate_form_names:
                new_form['name'] = translate_label(form['name'], lang, cache).replace("'", "\'")
                # let's ensure the input form name is unique!
                if new_form['name'] == form['name']:
                    new_form['name'] += ' (%s)' % lang

                print(f'new form name is now {new_form["name"]}')

            new_form_vars = []
            for form_var in form_vars:
                if 'label' in form_var:
                    old_label = form_var['label']
                    new_label = translate_label(form_var['label'], lang, cache)
                    print(f'{old_label} is now {new_label}')
                    form_var['label'] = new_label
                new_form_vars.append(form_var)

            new_form['json'] = quote(json.dumps(new_form_vars).encode('utf-8'))
            input_form_obj['form'] = new_form
            new_form_data[input_form_id] = json.dumps(input_form_obj)

    translated_screen['input_forms'] = new_form_data

    return translated_screen


def translate_label(label, lang, cache):
    """
    Use the google translate API to translate the label to the destination language
    :param label: label string to translate
    :param lang: destination language
    :param cache: cache object to cache the translations
    :return: translated label
    """
    global translator

    if translator == '':
        translator = Translator()

    if lang not in cache:
        cache[lang] = dict()

    if label not in cache[lang]:
        r = translator.translate(label, dest=lang)
        cache[lang][label] = r.text
    else:
        print('cache hit')

    return cache[lang][label]


def save_new_screen(new_screen_data, lang, cache, translate_screen_name=False):
    """
    Save screen data to a new file
    :param new_screen_data: fully processed screen data structure
    :param lang: destination language
    :param cache: translation cache
    :param translate_screen_name: translate screen name as well?
    :return: None
    """

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print('saving new screen')
    if 'screen' in new_screen_data:
        if 'name' in new_screen_data['screen']:
            name = new_screen_data['screen']['name']
            description = new_screen_data['screen']['description']

            if translate_screen_name:
                new_screen_data['screen']['name'] = translate_label(name, lang, cache)

            new_screen_data['screen']['description'] = f'{description} {lang}'
            new_screen_data['screen']['id'] = str(uuid.uuid4())
            new_name = f'{name} {lang}.json'
            new_path = os.path.join(output_dir, new_name)
            with open(new_path, 'w') as new_screen_file:
                new_screen_json = json.dumps(new_screen_data)
                new_screen_file.write(new_screen_json)
                print('All done')


if __name__ == '__main__':

    # what is this tool called again?
    tool_name = os.sys.argv[0]

    if len(os.sys.argv) < 3:
        print(f'Usage: {tool_name} exported_screen.json language')
        print(f'Example: {tool_name} exported_screen.json es')
        os.sys.exit(1)

    # what is the path to the screen file we want to process?
    screen_file_name = os.sys.argv[1]

    # what is the language code we want to translate to?
    language = os.sys.argv[2]

    # sanity check on existence of file
    if not os.path.exists(screen_file_name):
        print(f'{screen_file_name} was not found!')
        os.sys.exit(1)

    # explicitly define the translation cache here
    translation_cache = dict()

    try:
        # save all our translation API call results to be re-used if necessary
        translation_cache = load_translation_cache(cache_file_path)

        # process the file to pull out the data and verify it's structured properly
        screen_data_dict = get_screen_data_from_file(screen_file_name)

        # verify this is in fact an english language file
        if is_english(screen_data_dict):
            # now do the work
            new_screen = process_screen(screen_data_dict, language, translation_cache, True)
            # save the results to a new file
            save_new_screen(new_screen, language, translation_cache)

    finally:
        # no matter what, let's save whatever translation work we've already done
        if save_translation_cache(cache_file_path, translation_cache):
            print('Saved the cache!')

