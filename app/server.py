from flask import Flask
from flask import render_template, render_template_string, redirect, url_for
from flask import Response, request, jsonify
app = Flask(__name__)
from utils import *
import json
import os
import ast

# database/ and uploads/ are resolved relative to this directory, whatever the working directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# OpenAI credentials: export OPENAI_API_KEY (and optionally OPENAI_ORG_ID) before starting the server
from openai import OpenAI

client = OpenAI(
    api_key=os.environ.get("OPENAI_API_KEY"),
    organization=os.environ.get("OPENAI_ORG_ID") or None
)

# Chat model for every route. The user study ran on gpt-4-turbo and gpt-4; set JUMPSTARTER_MODEL to use another model.
MODEL = os.environ.get("JUMPSTARTER_MODEL", "gpt-4o")

#for dalle
import json
from base64 import b64decode
from pathlib import Path


def context_curation_fork(main_purpose, task_name, task_description, user_context):
    """
    Input: 
        main_purpose: a string (e.g. "I want to apply for a PhD in Computer Science")
        task_name: a string (e.g. "Identify potential programs")
        task_description: a string (e.g. "Identify potential programs that align with your research interests")
        user_context: a JSON object (key: context variable, value: the actual context value)
            e.g. {"CV_Bob": "ACTUAL Bob's CV CONTENT"}
    Output: a list of strings (context variables) from the user context
    """
    context = []
    prompt = """My user has a main purpose: {main_purpose}. My user is working on the task {task_name}: {task_description}. My user needs to break down the task into sub-tasks. Here is the current context history from the user: {context_history}. Please select the most relevant context key from the current context history that can be used to better decompose the current task into several sub-tasks for the user to get started. Do not help the user to break down the task. Please also provide explanations. Format the response like this: <context_key> \n \n <reasons>. Replace the context_key with the actual key in the context history.""".format(main_purpose=main_purpose, task_name=task_name, task_description=task_description, context_history=user_context)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": ''},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096
    )

    answer = output.choices[0].message.content.strip()
    answer = answer.split("\n")[0].strip()
    # remove quotes from answer
    answer = answer.replace('"', '')
    context.append(answer)

    return context

def gpt_parser_for_fork(context_info):
    """
    Input: 
        context_info: a string - raw answer draft saved by the user
    Output: a string - parsed context information for forking
    """
    sys_prompt = """You will be given an answer draft as input. You should output the key topic for each item in the answer draft and separate it by '\n'."""
    user_prompt = """Input: {raw_answer_draft} \n Output: """.format(raw_answer_draft=context_info)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=256
    )

    answer = output.choices[0].message.content.strip()

    return answer

@app.route('/get_general_steps', methods=['GET', 'POST'])
def get_general_steps():
    data = request.get_json()
    query = data["query"]
    prompt = "Give me a list of general steps related to "+query+". Format it like this: \n 1. step one \n 2. step two \n 3. step three. Do not include any details, just the general steps."
    print(query)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant to answer query related to AI PhD applications."},
            {"role": "user", "content": prompt},
        ]
    )

    response = output.choices[0].message.content

    return jsonify({
        "response": response
    })

@app.route('/get_emotional_support', methods=['GET', 'POST'])
def get_emotional_support():
    data = request.get_json()
    query = data["query"]
    prompt = "I am having trouble with {}. Can you provide me with some emotional support? Format it like this: \n 1. one \n 2. two \n 3. three.".format(query)
    # prompt = "Give me a list of general steps related to "+query+". Format it like this: \n 1. step one \n 2. step two \n 3. step three. Do not include any details, just the general steps."
    print(prompt)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant to answer query related to AI PhD applications."},
            {"role": "user", "content": prompt},
        ]
    )

    response = output.choices[0].message.content

    return jsonify({
        "response": response
    })

@app.route('/get_detailed_steps', methods=['GET', 'POST'])
def get_detailed_steps():
    data = request.get_json()
    query = data["query"]
    prompt = "Give me a detailed timeline related to "+query+". Format it like this: \n 1. date one: details related to date one \n 2. date two: details related to date two  \n 3. date three: details related to date three . Include details for each date. Please directly give me the specific date and details to do for that date, do not include any other information. Replace date one, date two, date three with your own dates."
    print(query)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant to answer query related to AI PhD applications."},
            {"role": "user", "content": prompt},
        ]
    )

    response = output.choices[0].message.content

    return jsonify({
        "response": response
    })

@app.route('/request_context_info', methods=['GET', 'POST'])
def request_context_info():
    data = request.get_json()
    # let data = {"advisorName":advisorName,"moreInfo":moreInfo}
    advisorName = data["advisorName"]
    moreInfo = data["moreInfo"]

    prompt = "I am writing an email to request a letter of recommendation from {}. Here is more information about myself: {}. Give me a list including what I need to add in the email. Do not give me an example email.".format(advisorName, moreInfo)
    print(prompt)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant to answer query related to AI PhD applications."},
            {"role": "user", "content": prompt},
        ]
    )

    response = output.choices[0].message.content

    print("response: ", response)

    return jsonify({
        "response": response
    })


@app.route('/get_started_all', methods=['GET', 'POST'])
def get_started_all():
    # Access the file if there is one
    
    # data = json.loads(request.form['jsonData'])
    data = request.get_json()
    # print(data)
    

    purpose = data["purpose"]
    sub_goal = data["sub_goal"]
    answer_draft = data["answer_draft"]
    # prev_answer_draft = data["prev_answer_draft"]
    # prev_sub_goal = data["prev_sub_goal"]
    curr_tree_texts = data["curr_tree_texts"]
    deadline = data["deadline"]
    description = data["description"]
    prompt_queries = data["prompt_queries"]
    action = data["action"]
    filenames = data["filenames"]  # string of list
    context = data["context"]  # $interview$
    system_prompt = data["sys_prompt"]

    print("Context from get_started_all: ", context)

    # convert a string list into list: "[1, 2]" -> [1, 2]
    filenames = ast.literal_eval(filenames)

    info = ""
    if filenames:
        for filename in filenames:
            with open('./uploads/' + filename, 'r') as file:
                info += file.read()

    # detect if context is not a string -> user context as object (root node context elicitation)
    # check if context starts with $
    if context.startswith('$'):
    # if '$' in context:
        # remove $$ from the context
        contexts = context.split(",")
        context_info = get_context_info_for_gpt_response(contexts)
    else:
        context_info = context

    sys_prompt = gpt_prompt_parse(data, system_prompt, user_info=info)
    # if info:
    #     sys_prompt = "My user's background information is as follows: {} \n \n. My user has a main purpose: {}.".format(info, purpose)
    # else:
    #     sys_prompt = "My user has a main purpose: {}.".format(purpose)

    print("Context info: ", context_info)
    if context_info:
        sys_prompt += " Please consider the following context information from my user: {}".format(context_info)
    
    # prompts = []
    # for i, action in enumerate(actions):
    #     prompt = gpt_prompt_parse(data, prompt_queries[i])
    #     prompts.append(prompt)

    prompt = gpt_prompt_parse(data, prompt_queries[0])
    print(sys_prompt)
    print(prompt)
    

    # create an empty dict to store the responses
    if action == "steps":
        responses = {
            "response_steps": ""
        }
    else:
        responses = {
            "response_brainstorm": ""
        }
    # responses = {
    #     # "response_steps": "",
    #     # "response_framework_brainstorm": "",
    #     "response_brainstorm": "",
    #     # "response_draft": ""
    # }

    # for i, action in enumerate(actions):
    #     output = client.chat.completions.create(
    #         model=MODEL,
    #         messages=[
    #             {"role": "system", "content": sys_prompt},
    #             {"role": "user", "content": prompts[i]},
    #         ],
    #         max_tokens=4096
    #     )

    #     response = output.choices[0].message.content
    #     responses["response_" + action] = response

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096
    )

    response = output.choices[0].message.content
    responses["response_" + action] = response

    return jsonify(responses)

@app.route('/fork_detection', methods=['GET', 'POST'])
def fork_detection():
    data = request.get_json()
    # description = data["query"]  # descriptions of the node
    main_purpose = data["main_purpose"]
    task_name = data["task_name"]
    description = data["description"]  # descriptions of the node
    user_context = data['user_context']
    print("User context: ", user_context)

    sys_prompt = """
    Given the queried task, determine if a "for" loop is needed to complete the task. You will be given a question Q. Please provide the reasoning and then respond with "Yes" or "No".
Here are some examples:
Q: Research the specific HCI PhD programs at each university from the initial list. Focus on aspects such as program curriculum, research opportunities, faculty expertise, and available resources.
Reason: The task requires a "for" loop to complete as there already exists an initial list of entities (i.e. universities) to research. Specifically, the goal of this task is to research the program curriculum, research opportunities, faculty expertise, and available resources for each university from the initial list. It is not possible to complete the task directly without a "for" loop.
A: Yes

Q: Make a list of potential recommenders including former supervisors, academic advisors, and professors who are familiar with your academic and research abilities.
Reason: The task does not require a "for" loop to complete as there does not exist a list of potential recommenders. The goal of this task therefore is to construct the list of recommenders based on certain criteria.
A: No

Q: Reach out to the individuals on your list via email or phone, providing them with the necessary documents and details about the HCI programs, and formally request their letters of recommendation
Reason: This task needs a "for" loop to complete as you have already obtained your list of individuals. You should reach out to each entity (i.e. individuals) on the list to complete the task.
A: Yes

Q: Gather information on different universities offering PhD programs in Human-Computer Interaction. Create an initial list based on general information such as program recognition, location, and basic offerings.
Reason: The task does not require a "for" loop to complete as there does not exist a list of universities offering PhD programs in HCI that can be used to iterate on.
A: No"""

    prompt = "Q: {}".format(description)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
        max_tokens=256
    )

    answer = output.choices[0].message.content.strip()
    answer = re.sub(r'\s*\n+', '\n', answer)
    response = "No"
    for ans in answer.split("\n"):
        if "A:" in ans:
            response = ans.split(":")[1].strip()
            break

    context = []  # context curated for forking: a list of strings (context variables)
    # if "Yes" -> fork node: context curation and find the relevant context from the context pool
    if response == "Yes" or response == "yes":
        context = context_curation_fork(main_purpose, task_name, description, user_context)  # a list of strings


    return jsonify({
        "answer": response,  # "Yes" or "No"
        "context_curation": context
    })

@app.route('/context_elicitation_draft', methods=['GET', 'POST'])
def context_elicitation_draft():
    data = request.get_json()
    main_purpose = data["main_purpose"]
    task_name = data["task_name"]
    task_description = data["task_description"]
    user_context = data["user_context"]

#     prompt = """My user has a main purpose: {main_purpose}. My user is working on the task {task_name}: {task_description}. The current context history from the user is {context_history}. Please judge if the current context information is enough to do this task. If not, what existing most important extra information do you think they should provide as the context information for this task? Please directly generate questions for users to answer as extra info. Otherwise, output "Ready"
# Format the response like this: 1. <question 1> : <reason for asking question 1> -> title of question 1
# 2. <question 2> : <reason for asking question 2> -> title of question 2 
# 3. <question 3> : <reason for asking question 3> -> title of question 3 """.format(main_purpose=main_purpose, task_name=task_name, task_description=task_description, context_history=user_context)

    prompt = """My user has a main purpose: {main_purpose}. My user is working on the task {task_name}: {task_description}. The current context history from the user is {context_history}. What existing most important extra information do you think they should provide as the context information for this task? Please directly generate questions for users to answer as extra info.
    Format the response like this: 1. <question 1> : <reason for asking question 1> -> title of question 1
    2. <question 2> : <reason for asking question 2> -> title of question 2 
    3. <question 3> : <reason for asking question 3> -> title of question 3 """.format(main_purpose=main_purpose, task_name=task_name, task_description=task_description, context_history=user_context)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": ''},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096
    )

    answer = output.choices[0].message.content.strip()

    print(answer)

    # parse the answer to get the object: key (title), value (description)
    if answer == "Ready" or answer == "ready":
        context = {}
        print("Ready! No Elicitated Context Needed ...")
    else:
        context = parse_context_elicitation(answer)  # {title: description}
        print("Elicitated Context from context_curation_draft: ", context)

    return jsonify({
        "context": context
    })

@app.route('/context_curation_draft', methods=['GET', 'POST'])
def context_curation_draft():
    data = request.get_json()
    main_purpose = data["main_purpose"]
    task_name = data["task_name"]
    task_description = data["task_description"]
    user_context = data["user_context"]

    print("task name: ", task_name)
    print("task description: ", task_description)
    print("user context: ", user_context)

    sys_prompt = """Given the user's main purpose and the task they are working on, select the most relevant context keys from the current context history that can be used to draft good responses for the user to complete the task. Please also provide explanations. \n The current context history is shown as one or more key-value pairs. Please select only the keys from the 'key' part of the context history. Do not select the keys from the 'value' part of the context history \n Format the response like this: number. <context_keys> -> <reasons for selecting context_keys>. Replace the context_keys with the actual keys as shown in the context history. Please directly give the answers and do not provide extra summarization sentences at the end. Please ensure to output one context key per line and do not merge different keys into the same line."""

    prompt = """My user has a main purpose: {main_purpose}. My user is working on the task {task_name}: {task_description}. Here is the current context history in JSON format (with 'key':'value' pairs) from the user: {context_history}.""".format(main_purpose=main_purpose, task_name=task_name, task_description=task_description, context_history=user_context)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096
    )

    answer = output.choices[0].message.content.strip()

    # parse the answer to get the list of context keys
    context = parse_context_curation(answer)  # {title: reasons}
    context = [key for key in context.keys()]

    print("Curated context: ", context)

    # remove the leading and trailing single and double quotes in each context key in the list -> c.strip('\'"') for c in s
    context = [c.strip('\'"') for c in context]

    # remove the leading and trailing single and double * in each context key in the list
    context = [c.strip('*') for c in context]
    
    return jsonify({
        "context": context 
    })

@app.route('/context_curation_breakdown', methods=['GET', 'POST'])
def context_curation_breakdown():
    data = request.get_json()
    main_purpose = data["main_purpose"]
    task_name = data["task_name"]
    task_description = data["task_description"]
    user_context = data["user_context"]

    # TODO: work on this later
    context = []
    prompt = """My user has a main purpose: {main_purpose}. My user is working on the task {task_name}: {task_description}. My user needs to break down the task into sub-tasks. Here is the current context history from the user: {context_history}. Please select the most relevant context keys from the current context history that can be used to better break down the current task into several sequential sub-tasks for the user to get started. If there is no such context, please return NONE. Please also provide explanations.
    """
    # context = context_curation_fork(main_purpose, task_name, task_description, user_context)

    return jsonify({
        "data": "none"
    })

@app.route('/get_fork_steps', methods=['GET', 'POST'])
def get_fork_steps():
    data = request.get_json()
    context = data["context"]
    description = data["description"]
    duration = data['duration']

    print("In get_fork_steps: ")
    contexts = context.split(",")
    context_info = get_context_info_for_fork(contexts)  # raw answer draft
    print("Raw answer draft: ", context_info)

    # GPT parser for forking
    context_info = gpt_parser_for_fork(context_info)
    print("Parsed context info: ", context_info)

    # rewrite descriptions to make it specific to the context_info
    sys_prompt = "Given a description D and an entity E, rewrite D so that it is specific to E."
    context_lines = context_info.split('\n')
    context_descriptions = []
    for cl in context_lines:
        prompt = "D: {} \n E: {}".format(description, cl)
        try:
            output = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": prompt},
                ],
                max_tokens=256
            )
            response = output.choices[0].message.content
            context_descriptions.append(response)
        except Exception as e:
            context_descriptions.append("")

    # Get duration for the fork steps
    fork_duration = ""
    sys_prompt_fd = """You will be given a duration D, please decompose it into S sub-durations. Please directly generate the output.

    Here are two example:
    D: 1 day
    S: 4
    Output: 6 hours

    D: 1-2 months
    S: 8
    Output: 0.5-1 week

    Now start predicting:"""
    prompt_fd = """D: {}\nS: {}\n Output:""".format(duration, len(context_lines))
    
    try:
        output = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": sys_prompt_fd},
                {"role": "user", "content": prompt_fd},
            ],
            max_tokens=256
        )
        response = output.choices[0].message.content
        fork_duration = response.strip()
    except Exception as e:
        fork_duration = duration

    return jsonify({
        "response": context_info,
        "descriptions": context_descriptions,
        "duration": fork_duration
    })

@app.route('/get_started', methods=['GET', 'POST'])
def get_started():
    # Access the file if there is one
    # file = None
    # cv = ""
    # if 'file' in request.files:
    #     file = request.files['file']
    #     file.save('./uploads/' + file.filename)
    #     print(file.filename)
    #     print(file)
    #     # read the file as a string
    #     with open('./uploads/' + file.filename, 'r') as file:
    #         cv = file.read()
    #         print(cv)
    # else:
    #     with open('./uploads/CV_XuanmingZhang.txt', 'r') as file:
    #         cv = file.read()
    #         print(cv)

    # data = json.loads(request.form['jsonData'])
    data = request.get_json()
    # print(data)

    # data = request.get_json()
    query = data["query"]
    purpose = data["purpose"]
    action = data["action"]
    sub_goal = data["sub_goal"]
    answer_draft = data["answer_draft"]
    # prev_answer_draft = data["prev_answer_draft"]
    # prev_sub_goal = data["prev_sub_goal"]
    curr_tree_texts = data["curr_tree_texts"]
    deadline = data["deadline"]
    description = data["description"]  # TODO: use this in prompt later
    filenames = data["filenames"]
    # check if filenames is a list
    if isinstance(filenames, str):
        filenames = ast.literal_eval(filenames)
    context = data["context"]  # $interview$
    system_prompt = data["sys_prompt"]
    
    print("Context from regenerate: ", context)
    # print(query)

    prompt = gpt_prompt_parse(data, query)

    # getting fileuploads from the user
    info = ""
    if filenames:
        # print(filenames)
        for filename in filenames:
            with open('./uploads/' + filename, 'r') as file:
                info += file.read()
    print(info)

    # load uploaded_files.json: TODO: write this in a sperate database
    # if os.path.exists('database/uploaded_files.json'):
    #     with open('database/uploaded_files.json', 'r') as file:
    #         uploaded_files = json.load(file)
    # else:
    #     uploaded_files = {}

    # load drafts.json: TODO: write this in a sperate database
    # if os.path.exists('database/drafts.json'):
    #     with open('database/drafts.json', 'r') as file:
    #         drafts = json.load(file)
    # else:
    #     drafts = {}

    # if action == "steps":
    #     action_format =  "1. deadline date for step one: details of step one \n 2. deadline date for step two: details of step two \n 3. deadline date for step three: details of step three. Replace step one, step two, step three with your own steps and deadline date with your date. Please use month/day/year format for the deadline date."
    # elif action == "framework_brainstorm":
    #     action_format = "1. Brainstorm area one \n 2. Brainstorm area two \n 3. brainstorm area three. Replace area one, area two and area three with your own brainstorm areas. There can be more than three areas.".format(sub_goal, query)
    # elif action == "brainstorm":
    #     action_format = "In the past, someone used to achieve the sub-goal: {}. Details of how this person achive the sub-goal. Replace someone with a name. Complete the details of how this person achieve the sub-goal. Please provide the details only for {}.".format(sub_goal, sub_goal)
    # elif action == "draft":
    #     action_format = "Please directl provide the draft for the sub-goal: {}. You can make up the draft if no profile is provided.".format(sub_goal)
    # prompt = "My user has a purpose of {}. They need help with the specific steps with {}. They need help getting started. Please provide them with a draft of text they can customize with, or a list of simple questions they can answer to get going, or a suggestion of a writing activity you would need to help them move forward".format(purpose, query)

    sys_prompt = gpt_prompt_parse(data, system_prompt, user_info=info)
    # if info:
    #     sys_prompt = "My user's background information is as follows: {} \n \n. My user has a main purpose: {}.".format(info, purpose)
    # else:
    #     sys_prompt = "My user has a main purpose: {}.".format(purpose)

    # detect if context is not a string -> user context as object (root node context elicitation)
    if context.startswith('$'):
    # if '$' in context:
        # remove $$ from the context
        contexts = context.split(",")
        context_info = get_context_info_for_gpt_response(contexts)
    else:
        context_info = context
    # for context in contexts:
    #     context = context.strip()
    #     context = context.replace("$", "")
    #     if context in uploaded_files:
    #         filename = uploaded_files[context]['filename']
    #         description = uploaded_files[context]['filedescription']
    #         with open('./uploads/' + filename, 'r') as file:
    #             context_info += ' ' + description + file.read()
    print("Context info: ", context_info)
    if context_info:
        sys_prompt += " Please consider the following context information from my user: {}.".format(context_info)

    print(sys_prompt)
    print(prompt)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
        max_tokens=4096
    )

    response = output.choices[0].message.content
    print(response)

    return jsonify({
        "response": response
    })

@app.route('/synthesize', methods=['GET', 'POST'])
def synthesize():
    data = request.get_json()
    purpose = data["purpose"]
    query = data["query"]
    answer_draft = data["answer_draft"]
    brainstorm_texts = data["brainstorm_texts"]
    sub_goal = data["sub_goal"]

    prompt = "My user has a main purpose of {}. They need help with {}. Their current answer is {} for the sub-goal. Consider the brainstorm ideas below: {}. Please synthesize an answer regarding the user query {}. Please directly give the response.".format(purpose, sub_goal, answer_draft, brainstorm_texts, query)
    # prompt = "My user has a main purpose of {}. They need help with {}. Their current answer is {}. They need help iterating their answer. What do you suggest they do next? Please provide the response like this: {} Please directly give the response.".format(purpose, query, answer_draft, action_format)

    print(prompt)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant to answer query related to AI PhD applications."},
            {"role": "user", "content": prompt},
        ]
    )

    response = output.choices[0].message.content

    return jsonify({
        "prompt": prompt,
        "response": response
    })

@app.route('/regenerate', methods=['GET', 'POST'])
def regenerate():
    data = request.get_json()
    query = data["query"]
    draft = data["draft"]

    prompt = "My user has an initial draft: {}. Now, please regenerate the draft based on my user's query: {}.".format(draft, query)

    print(prompt)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant to answer query related to AI PhD applications."},
            {"role": "user", "content": prompt},
        ]
    )

    response = output.choices[0].message.content

    return jsonify({
        "prompt": prompt,
        "response": response
    })

@app.route('/chatresponse', methods=['GET', 'POST'])
def chatresponse():
    data = request.get_json()
    if len(data['chat_history']) == 0:
        chat_history = ""
        sys_prompt = "You are a helpful assistant to answer query related to AI PhD applications. My user has a main purpose: {}.".format(data['purpose'])
    else:
        chat_history = print_chat_history(data['chat_history'])
        sys_prompt = "You are a helpful assistant to answer query related to AI PhD applications. My user has a main purpose: {}. Here is the previous chat history: {}. Please response based on the chat history.".format(data['purpose'], chat_history)
    prompt = data["prompt"]
    prompt = gpt_prompt_parse(data, prompt)
    print(prompt)

    print(sys_prompt)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ]
    )

    response = output.choices[0].message.content

    return jsonify({
        "response": response
    })

@app.route('/uploadUserContextFile', methods=['POST'])
def uploadUserContextFile():
    data = json.loads(request.form['jsonData'])
    label_key = data["label_key"]

    fileContent = ''
    if 'file' in request.files:
        file = request.files['file']
        file.save('./uploads/' + file.filename)
        print("Uploaded user context file: ", file.filename)
        # read the file as a string
        with open('./uploads/' + file.filename, 'r') as file:
            fileContent = file.read()

    return jsonify({
        "fileContent": fileContent
    })

@app.route('/submit_draft_and_upload_files', methods=['POST', 'GET'])
def submit_draft_and_upload_files():

    data = json.loads(request.form['data'])

    draft_name = data["draft_name"]
    answer_draft_input = data["answer_draft"]
    file_id = data["file_id"]
    filedescription = data["filedescription"]
    message = {
        "answer_draft": "draft submission failed",
        "files": "file upload failed"
    }

    # upload files if there exists
    filename = ''
    if 'file' in request.files:
        file = request.files['file']
        file.save('./uploads/' + file.filename)
        filename = file.filename
        uploaded_files = get_and_update_uploaded_files(file_id, filename, filedescription)
    # if os.path.exists('database/uploaded_files.json'):
    #     with open('database/uploaded_files.json', 'r') as file:
    #         uploaded_files = json.load(file)
    # else:
    #     uploaded_files = {}
    # uploaded_files[file_id] = {'filename': filename, 
    #                             'filedescription': filedescription}
    # with open('database/uploaded_files.json', 'w') as file:
    #     json.dump(uploaded_files, file, indent=4)

    # save the global drafts
    _, _, message = get_and_update_global_drafts(draft_name, answer_draft_input, file_id, filename, filedescription, message)

    return jsonify(message)

@app.route('/submit_file', methods=['POST', 'GET'])
def submit_file():
    # {sub_goal: {'filename': filename, 
    #             'filedescription': filedescription'}}

    data = json.loads(request.form['data'])
    print(data)

    file_id = data["file_id"]  # user-specific file id
    filedescription = data["filedescription"]
    sub_goal = data["sub_goal"]
    filename = ""

    if 'file' in request.files:
        file = request.files['file']
        file.save('./uploads/' + file.filename)
        filename = file.filename
        print(file.filename)
        print(file)
        # read the file as a string
        # with open('./uploads/' + file.filename, 'r') as file:
        #     cv = file.read()
        #     print(cv)

    if os.path.exists('database/uploaded_files.json'):
        with open('database/uploaded_files.json', 'r') as file:
            uploaded_files = json.load(file)
    else:
        uploaded_files = {}
    
    uploaded_files[file_id] = {'filename': filename, 
                                'filedescription': filedescription}
    
    with open('database/uploaded_files.json', 'w') as file:
        json.dump(uploaded_files, file, indent=4)

    return jsonify({
        "message": "File uploaded successfully"
    })

@app.route('/detect_subtasks', methods=['GET', 'POST'])
def detect_subtasks():
    data = request.get_json()
    node_text = data["node_text"]
    description = data["description"]

    sys_prompt = """ You are a useful assistance to detect if the current task needs to be further decomposed if it is not actionable and the primary goal of the task can not be viewed as a singular, distinctive deliverable. Based on the user prompt, please output Yes if it needs to be decomposed; No otherwise meaning it is actionable and does not require task decomposition. Please also provide explanations for your choice. \n\n Here are some examples: \n User: My user is working on the task Research on Prospective Companies and Positions: Conduct a comprehensive search on potential companies and specific research scientist internship positions in the NLP field. Understand what each role entails, identify skill requirements, and evaluate how they align with your research interests. My user needs to know if the current task is specific and actionable \n Reason: this task needs to be further decomposed as it involves more than one deliverables: search on companies and search on positions. To complete this task, there are multiple subtasks that need to be done separately. These include conducting a comprehensive search on potential companies, searching for specific research scientist internship positions, an analysis of what each role entails, identifying skill requirements, and evaluation of alignment with the user's research interests. \n Answer: Yes \n\n User: My user is working on the task Identify Potential Universities: Create a list of universities that offer PhD programs in HCI. The selection can be based on factors such as reputation, HCI research focus, published HCI research papers, faculty expertise etc. My user needs to know if the current task is specific and actionable. \n Reason: This task does not need to be further decomposed as it just involves one deliverable: create a list of schools that offer PhD programs in HCI. Although it may require several steps to create the list, the end goal of this task is to get a list. Therefore the task is actionable. \n Answer: No \n\n User: My user is working on the task Identify Required Documents: Reseach and confirm all the necessary documents required for the non-driver ID application, ensuring to list all forms of acceptable proofs such as a birth certificate or passport for identity, Social Security Card or W-2 form for Social Security number, and utility bills or lease agreement for proof of residency. My user needs to know if the current task is specific and actionable.  \n Reason: The primary goal of the task is to identify necessary documents for the non-driver ID application, which can be viewed as a singular, cohesive deliverable. Despite involving various types of documents, the task is focused on compiling a comprehensive list, which makes it actionable as a single unit. The distinction lies in the focus on gathering all necessary documentation, a clear and direct objective. \n Answer: No \n\n  Now, let's start prediction: 
    """
    user_prompt = """My user is working on the task {}: {}. My user needs to know if the current task needs to be decomposed.""".format(node_text, description)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=4096
    )

    answer = output.choices[0].message.content.strip()
    print(answer)
    answer  = re.sub(r'\s*\n+', '\n', answer)
    response = "No"
    for ans in answer.split("\n"):
        if not "Reason:" in ans:
            if "Answer:" in ans:
                response = ans.split(":")[1].strip()
                break
            else:
                response = ans.strip()
                break
        

    # answer = answer.split("\n")[0].strip()  # "Answer: No"
    # if ":" in answer:
    #     answer = answer.split(":")[1].strip()

    return jsonify({
        "response": response
    })

@app.route('/home')
def home():
    # you can pass in an existing article or a blank one.
    username = request.args.get('username')
    return render_template('home.html', username=username)

@app.route('/')
def index():
    return render_template('login.html', message='')

@app.route('/login', methods=['POST'])
def login():

    # get the database for users
    users_info = get_users_info()

    username = request.form['username']
    password = request.form['password']

    if username in users_info and users_info[username] == password:
        return redirect(url_for('home', username=username))
    elif username not in users_info:
        # update users.json with the new user: {username: password}
        users_info[username] = password
        print(users_info)
        with open('database/users_info.json', 'w') as file:
            json.dump(users_info, file, indent=4)
        return redirect(url_for('home', username=username))
        # return render_template('login.html', message='User does not exist')
    else:
        return render_template('login.html', message='Invalid username or password')

@app.route('/elicit_context_root', methods=['GET', 'POST'])
def elicit_context_root():
    # init elicit context root route

    # username = request.form['username']
    data = request.get_json()
    task_input = data['task']

    sys_prompt = """You are a helpful assistant in generating at most three questions to elicit more context from the user in order to accomplish a task the user is involved. You will be given the main purpose of the task, and the current context history from the user. You need to judge if the current context information is enough to do this task. If not, what existing doc do you think they already have and can be provided as the context document for this task? Alternatively, what existing most important extra information do you think they should provide as the context information for this task? Please try your best to start by asking the potential existing doc first, and then ask for the potential info. Do not ask the question that can be possibly answered from the suggested doc in the first question. You can also just ask for the potential info if no doc is needed from the user. Please directly generate the questions for users to answer, provide the reason for the question, identify if it is DOC or INFO, and provide a name for the question. Otherwise, output "Ready".

Here are two examples:
Input: My user has a main purpose: Apply for a drivers license by 12/15/2024. The current context history from the user is empty.
Output:
1. Reason: Driver's license requirements vary significantly depending on the location. Knowing the specific state or country would allow for tailored advice regarding local rules, tests, and documentation required -> Question:  Which state or country are you applying for? -> Type: INFO -> Name: State or Country
2. Reason: Different age groups may have different requirements or steps in the licensing process. For example, minors often have to go through graduated license programs. -> Question: How old are you -> Type: INFO -> Name: Age of the User

Input: My user has a main purpose: Apply for a PhD program by 12/15/2024. The current context history from the user is empty.
Output:
1. Reason: Curriculum Vitae (CV) or Resume could be helpful as it would likely contain detailed information about their educational background and any research experiences or academic achievements, which are critical for applying to PhD programs. -> Question: What CV or Resume can you provide for the PhD application? -> Type: DOC -> Name: CV or Resume

Now, start prediction:"""

    prompt = """Input: My user has a main purpose: {task_input}. The current context history from the user is empty.""".format(task_input=task_input)

    output = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": prompt},
        ],
        max_tokens=512
    )

    answer = output.choices[0].message.content.strip()  # """Reason: Knowing the field or industry in which the user is seeking an internship is crucial as it determines the specific skills, experiences, and qualifications that might be necessary to highlight in their application. Answer: What field or industry are you looking to apply for an internship in? \n Type: INFO."""

    # parse the answer to get the object: key (title), value (description)
    context = parse_context_root(answer)  # {title: description}
    print("Elicitated Context: ", context)

    return jsonify({
        "context": context
    })


@app.route('/task', methods=['POST'])
def task():

    # print(request.files)
    # take hidden input from the form
    username = request.form['username']
    task_input = request.form['task_input']

    # initialize user context
    userGlobalContext = {}
    # iterativley get the context info and files
    print("Print context info: --------------")
    customname = ""
    for contextName, contextContent in request.form.items():
        if contextName != "username" and contextName != "task_input":
            print(f"{contextName}: {contextContent}")
            if contextContent:
                if contextName == "customName":
                    customname = contextContent  # e.g. context Content: CV
                    userGlobalContext[contextContent] = request.form['customContent']
                else:
                    if contextName != 'customContent':
                        userGlobalContext[contextName] = contextContent

    print("Print files: --------------")
    for key, file in request.files.items():
        if file:
            print(f"{key}: {file.filename}")
            # print the file content
            file.save(f"./uploads/{file.filename}")
            with open(f"./uploads/{file.filename}", 'r') as f:
                if key == "customFile":
                    # save the custom file as strings to the user context
                    if customname in userGlobalContext:
                        userGlobalContext[customname] += f.read()
                    else:
                        userGlobalContext[customname] = f.read()
                else:
                    contextName = key.split('File')[0].strip()
                    if contextName in userGlobalContext:
                        userGlobalContext[contextName] += f.read()
                    else:
                        userGlobalContext[contextName] = f.read()

    print("User global context: ", userGlobalContext)

    # check if file is in the request
    # uploaded_files = []
    # for file in files:
    #     if file.filename != '':
    #         file.save('./uploads/' + file.filename)
    #         uploaded_files.append(file.filename)
    #         # save to user context: key(filename), value (file content)
    #         with open('./uploads/' + file.filename, 'r') as f:    
    #             user_context[file.filename] = f.read()
    # print(uploaded_files)

    return render_template('layout.html', task_input=task_input, filenames=[], root_node=None, username=username, userGlobalContext=userGlobalContext, user_context={})

@app.route('/task_continue', methods=['GET'])
def task_continue():
    username = request.args.get('username')
    taskId = request.args.get('taskId')
    print("Getting username: ", username)
    print("Getting task id: ", taskId)

    # Continue to do the task with the input taskId
    all_tasks = get_current_tasks()
    task = all_tasks[username][int(taskId)]
    task_input = task['task_input']
    filenames = task['filenames']
    # filenames = ast.literal_eval(filenames)
    root_node = task['root_node']  # this is a class instance json object
    user_context = task['user_context']  # this is a json object containing the current user context factory / pool (key-value pairs) for this task

    print("Task input: ", task_input)
    print("Filenames: ", filenames)
    print("Root node: ", root_node)
    print("User context: ", user_context)
    return render_template('layout.html', task_input=task_input, filenames=filenames, root_node=root_node, username=username, user_context=user_context)

@app.route('/save_task', methods=['POST'])
def save_task():
    data = request.get_json()
    print(data)
    task_input = data["task"]
    filenames = data["filenames"]
    filenames = ast.literal_eval(filenames)
    username = data["username"]
    userGlobalContext = data["userGlobalContext"]
    user_context = data["user_context"]
    print('Getting task input: ', task_input)
    print('Getting filenames: ', filenames)
    print('Getting username: ', username)
    print('Getting user global context: ', userGlobalContext)
    print('Getting user context: ', user_context)

    # get the root node
    root_node = data['root_node']
    # get the task json file {task_id: task_object}
    tasks = get_current_tasks()
    if username not in tasks:
        tasks[username] = [{
            "task_input": task_input,
            "filenames": filenames,
            "root_node": root_node,
            "userGlobalContext": userGlobalContext,
            "user_context": user_context
        }]
    else:
        tasks[username].append({
            "task_input": task_input,
            "filenames": filenames,
            "root_node": root_node,
            "userGlobalContext": userGlobalContext,
            "user_context": user_context
        })

    # # n_tasks = len(tasks)

    # assign the next task id
    # task_id = n_tasks

    # task_obj = {
    #     "task_input": task_input,
    #     "filename": filename,
    #     "root_node": root_node,
    # }

    # tasks[task_id] = task_obj

    # save the task json file
    with open('database/tasks.json', 'w') as file:
        json.dump(tasks, file, indent=4)

    return jsonify({
        "message": "Task saved successfully"
    })

@app.route('/get_tasks', methods=['GET'])
def get_tasks():
    username = request.args.get('username')
    tasks = get_current_tasks()

    if username and username in tasks:
        user_tasks = tasks[username]   # list of dictionaries
    else:
        user_tasks = []

    return jsonify(user_tasks)


if __name__ == '__main__':
    # app.run(debug = True, port = 4000)    
    # app.run(debug = True, port = 5003)
    # Set JUMPSTARTER_HOST=0.0.0.0 to serve other machines (the debugger stays on, so only on a trusted network)
    app.run(host=os.environ.get('JUMPSTARTER_HOST', '127.0.0.1'), port=55113, debug=True, use_reloader=False)
