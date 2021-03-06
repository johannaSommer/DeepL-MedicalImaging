import uuid
import json
from pathlib import Path
import os
import tensorflow as tf
from src.utils.storage import upload_file, download_file, delete_file


def save_model(model, history, name, filename, description, version='1', upload=True):
    # Author: Kristian & Tobias
    """
    Wrapper for the model.save function which logs the results

    Parameters:
    model (keras.model)
    history: the train history which is returned from the fit function
    name: the name of the model, defines also the folder where the model is saved
            (can be the same over different versions)
    filename: the filename of the model
    description: a description of the model
    version: the version of the model
    upload: whether the model should be uploaded to the gcp

    Returns:
    id string: the id of the model
    """

    if not model or not history:
        raise Exception('Hisory or model are not defined')

    CURRENT_WORKING_DIR = Path(os.getcwd())
    basepath = CURRENT_WORKING_DIR
    # path main directory
    if basepath.name != "idp-radio-1":
        basepath = basepath.parent.parent

    # transform hisory values from np.float32 to regular floats
    for key in history.keys():
        history[key] = [float(val) for val in history[key]]

    identifier = str(uuid.uuid1())
    log = {
        'id': identifier,
        'name': name,
        'filename': filename,
        'version': version,
        'history': history,
        'description': description,
        # the following properties should be set using the `model_set` function
        # after eveluating the model. See function for documentation.
        'test': None,
        'classification_report': None,
    }

    # append model data to log file
    data = None
    log_file = basepath / 'logs/unvalidated-experiment-log.json'
    try:
        with open(log_file, 'r') as f:
            data = json.load(f)
    except ValueError as error:
        print("WARNING: {log_file} could not be read as json and will be overwritten".format(
            log_file=log_file))
        print(error)

    # add experiments property to dict if the file was empty
    if not data or not 'experiments' in data:
        data = {'experiments': []}

    # check for exisiting model with same name and version
    for experiment in data['experiments']:
        if experiment['name'] == log['name'] and experiment['version'] == log['version']:
            log['version'] += 1
            print(
                'There is already a model with the same name and version. Increased version number.')

    data['experiments'].append(log)

    # save model
    folderpath = basepath / 'models' / name
    path_h5 = folderpath / filename
    path_tf = folderpath / filename.replace(".h5", "")

    # make sure path exists, ceate one if necessary
    Path(folderpath).mkdir(parents=True, exist_ok=True)
    model.save(path_h5, save_format="h5")
    model.save(path_tf, save_format="tf")

    with open(log_file, 'w') as f:
        json_data = json.dumps(data, indent=4)
        f.write(json_data)

    # upload model to gcp
    if upload:
        remote_name = log['id'] + '.h5'
        upload_file(str(path_h5), remote_name)

    return identifier


def model_set(identifier, attribute, value):
    # Author: Kristian
    """
    Util function to set attributes in the log of the model

    Valid attributes:
     test: List containing the test score and accuracy. Generated using the
           `model.evaluate_generator function
     classification_report: generated using `sklearn.metrics.classification_report`


    Parameters:
    identifier: the id of the model
    attribute: the attribute name one wants to set
    value: the value that is set

    Returns:
    id string: the id of the model
    """

    CURRENT_WORKING_DIR = Path(os.getcwd())
    basepath = CURRENT_WORKING_DIR
    # path to main directory
    if basepath.name != "idp-radio-1":
        basepath = basepath.parent.parent
    os.chdir(basepath)

    # append model data to log file
    data = None
    log_file = basepath / 'logs/unvalidated-experiment-log.json'
    try:
        with open(log_file, 'r') as f:
            data = json.load(f)
    except ValueError:
        print("WARNING: {log_file} could not be read as json and will be overwritten".format(
            log_file=log_file))

    # add experiments property to dict if the file was empty
    if not data or not 'experiments' in data:
        raise Exception('No models in log file')

    for model in data['experiments']:
        if model['id'] == identifier:
            model[attribute] = value

    with open(log_file, 'w') as f:
        json_data = json.dumps(data, indent=4)
        f.write(json_data)

    # reset workdir
    os.chdir(CURRENT_WORKING_DIR)

    return identifier


def load_model(identifier=None, name=None, version=None):
    # Author: Kristian
    """
     Loads a given model (by identifier or by name and version) from gcp-storage if its not
     loaded locally

     Parameters:
     identifier: the id of the model
     name: the name of the model
     version: the version of the model

     Returns:
     keras model
    """

    if not (identifier or (name and version)):
        raise Exception(
            'You must specify the id, or the name and version of the model')

    CURRENT_WORKING_DIR = Path(os.getcwd())
    basepath = CURRENT_WORKING_DIR
    # path main directory
    if basepath.name != "idp-radio-1":
        basepath = basepath.parent.parent

    # load logfile
    data = None
    log_file = basepath / 'logs/experiment-log.json'
    try:
        with open(log_file, 'r') as f:
            data = json.load(f)
    except ValueError:
        print("WARNING: {log_file} could not be read as json and will be overwritten".format(
            log_file=log_file))
    experiments = data['experiments']

    # append unvalidated experiments
    unvalidated_log_file = basepath / 'logs/unvalidated-experiment-log.json'
    with open(unvalidated_log_file, 'r') as f:
        experiments = experiments + json.load(f)['experiments']

    # reset workdir
    os.chdir(CURRENT_WORKING_DIR)

    experiment = find_experiment(experiments, identifier, name, version)

    if not experiment:
        raise Exception('Model was not found')

    # build model path
    folderpath = basepath / 'models' / experiment['name']
    exp_path = folderpath / experiment['filename']

    # download model if it does not exist
    if not os.path.isfile(exp_path):
        bucket_filename = experiment['id'] + '.h5'
        Path(folderpath).mkdir(parents=True, exist_ok=True)
        download_file(bucket_filename, exp_path)

    return exp_path


def delete_model(identifier=None, name=None, version=None):
    # Author: Kristian
    """
    Deletes a given model (by identifier or by name and version)

    Parameters:
    experiments: list of experiments
    identifier: the id of the model
    name: the name of the model
    version: the version of the model
    """

    if not (identifier or (name and version)):
        raise Exception(
            'You must specify the id, or the name and version of the model')

    # load logfile
    CURRENT_WORKING_DIR = os.getcwd()
    basepath = Path(CURRENT_WORKING_DIR)
    log_file = basepath / 'logs/experiment-log.json'

    experiment = None
    data = None

    # load validated models
    try:
        with open(log_file, 'r') as f:
            data = json.load(f)
    except ValueError:
        print("WARNING: {log_file} could not be read as json and will be overwritten".format(
            log_file=log_file))

    if data and 'experiments' in data:
        experiment = find_experiment(
            data['experiments'], identifier, name, version)

    # look for the model in the unvalidated experiment log
    if not experiment:
        log_file = basepath / 'logs/unvalidated-experiment-log.json'

        with open(log_file, 'r') as f:
            data = json.load(f)

        if data and 'experiments' in data:
            experiment = find_experiment(
                data['experiments'], identifier, name, version)

    if not experiment:
        raise Exception('The model was not found')

    # delete the model from the gcp storage
    delete_file(experiment['id'] + '.h5')

    # remove the experiment from the log and write it back to the logfile
    data['experiments'].remove(experiment)
    with open(log_file, 'w') as f:
        json_data = json.dumps(data, indent=4)
        f.write(json_data)

    # delete local instance of model if it exists
    foldername = basepath / 'models' / experiment['name']
    filename = foldername / experiment['filename']
    if os.path.isfile(filename):
        os.remove(filename)

    # reset workdir
    os.chdir(CURRENT_WORKING_DIR)


def find_experiment(experiments, identifier=None, name=None, version=None):
    # Author: Kristian
    """
    Helper function to find an experiment in a list

    Parameters:
    experiments: list of experiments
    identifier: the id of the model
    name: the name of the model
    version: the version of the model

    Returns:
    dict
    """

    for exp in experiments:
        if exp['id'] == identifier or (exp['name'] == name and exp['version'] == version):
            return exp
    return None


def get_experiment(identifier=None, name=None, version=None):
    # Author: Kristian
    """
    Helper function to find an experiment from the logs

    Parameters:
    experiments: list of experiments
    identifier: the id of the model
    name: the name of the model
    version: the version of the model

    Returns:
    dict
    """

    # load logfile
    CURRENT_WORKING_DIR = os.getcwd()
    basepath = Path(CURRENT_WORKING_DIR)
    log_file = basepath / 'logs/experiment-log.json'

    with open(log_file, 'r') as f:
        data = json.load(f)

    if data and 'experiments' in data:
        experiment = find_experiment(
            data['experiments'], identifier, name, version)

    # look for the model in the unvalidated experiment log
    if not experiment:
        log_file = basepath / 'logs/unvalidated-experiment-log.json'

        with open(log_file, 'r') as f:
            data = json.load(f)

        if data and 'experiments' in data:
            experiment = find_experiment(
                data['experiments'], identifier, name, version)

    return experiment
