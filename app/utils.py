import os
import json
import re


def gpt_prompt_parse(data, query, user_info=''):
    prompt = query.replace("$action$", data["action"])
    prompt = prompt.replace("$sub_goal$", data["sub_goal"])
    prompt = prompt.replace("$answer_draft$", data["answer_draft"])
    # prompt = prompt.replace("$prev_answer_draft$", data["prev_answer_draft"])
    # prompt = prompt.replace("$prev_sub_goal$", data["prev_sub_goal"])
    prompt = prompt.replace("$curr_tree_texts$", data["curr_tree_texts"])
    prompt = prompt.replace("$curr_parents$", data["curr_parents"])
    prompt = prompt.replace("$deadline$", data["deadline"])
    prompt = prompt.replace("$description$", data["description"])
    prompt = prompt.replace("$purpose$", data["purpose"])
    prompt = prompt.replace("$user_info$", user_info)
    prompt = prompt.replace("$context$", data["context"])

    return prompt

def print_chat_history(chat_history):
    """Input: chat_history: list of dictionaries"""
    """[{'user': "My purpose is $purpose$. What's your suggestions?"}, {'bot': "Sure, here are some general steps to help guide you through the process:1. **Understand the requirements**: Before you apply, you should understand the requirements of the program you are interested in. Requirements include a strong background in Computer Science, Mathematics, Statistics or a related area. A Masters degree might also be necessary but not always. Research experience can be a great plus.2. **Select universities**: Choose the universities where you would love to complete your PhD. This selection can be based on faculty, research facilities, funding options and location, among other factors. 3. **Identifying potential supervisors**: Within your selected universities, look for potential supervisors who are doing research in the field of NLP. Check their works published in recent years to see if their research aligns with your interest.4. **Preparation of documents**: Prepare necessary documents such as your CV, research proposal, personal statement etc. 5. **Letters of Recommendation**: Identify professors or professionals who know you well and can testify about your skills and potential to succeed in a PhD program.6. **GRE and TOEFL/IELTS**: If the program requires these test scores, make sure you do well in them. They offer the universities a way of comparing students from different countries on similar grounds.7. **Application**: Start applying to the universities before the deadline (12/15/24 in your case). Make sure to keep track of each school’s deadline and submission process to avoid last minute hiccups.8. **Interview preparation**: Prepare for potential interviews. They might ask you about your research interests, why you want to do a PhD or about your previous projects.9. **Regular follow up**: After you have submitted applications, periodically follow up on them. This will keep you informed about your application's status.10. **Plan B**: Always have a second plan if this doesn't work out. This could be work, another degree, or applying for other universities or programs.Remember, the process takes time and patience. Begin early and always keep checking if the universities have any upcoming webinars, virtual tours or other events that may help you to better understand the program and make your application stronger. Good luck!"}]"""
    output = ""
    for chat in chat_history:
        for key, value in chat.items():
            output += f"{key}: {value}\n"

    return output


def get_global_drafts():
    # load drafts.json: TODO: write this in a sperate database
    if os.path.exists('database/global_drafts.json'):
        with open('database/global_drafts.json', 'r') as file:
            global_drafts = json.load(file)
    else:
        global_drafts = {}

    return global_drafts

def get_draft_inputs():
    # load drafts.json: TODO: write this in a sperate database
    if os.path.exists('database/draft_inputs.json'):
        with open('database/draft_inputs.json', 'r') as file:
            draft_inputs = json.load(file)
    else:
        draft_inputs = {}

    return draft_inputs


def get_current_tasks():
    if os.path.exists('database/tasks.json'):
        with open('database/tasks.json', 'r') as file:
            tasks = json.load(file)
    else:
        tasks = {}

    return tasks

def get_users_info():
    if os.path.exists('database/users_info.json'):
        with open('database/users_info.json', 'r') as file:
            users_info = json.load(file)
    else:
        users_info = {}

    return users_info


def get_uploaded_files():
# load drafts.json: TODO: write this in a sperate database
    if os.path.exists('database/uploaded_files.json'):
        with open('database/uploaded_files.json', 'r') as file:
            uploaded_files = json.load(file)
    else:
        uploaded_files = {}

    return uploaded_files


def get_context_info_for_fork(contexts):
    draft_inputs = get_draft_inputs()

    output = ""
    for context in contexts:
        context = context.strip()
        context = context.replace("$", "")
        if 'answer-draft' in context:
            context_name = context.split('-answer-draft')[0]
            if context_name in draft_inputs:
                output += draft_inputs[context_name]
        # if context in drafts:
        #     output += drafts[context]['answer_draft_input'] + ' '

    return output


def get_context_info_for_gpt_response(contexts):
    global_drafts = get_global_drafts()
    draft_inputs = get_draft_inputs()
    uploaded_files = get_uploaded_files()
    print("Contexts: ", contexts)

    output = ""
    for context in contexts:
        context = context.strip()
        context = context.replace("$", "")
        if 'answer-draft' in context:
            context_name = context.split('-answer-draft')[0]
            if context_name in draft_inputs:
                output += draft_inputs[context_name]

        else:
            if context in uploaded_files:
                filename = uploaded_files[context]['filename']
                description = uploaded_files[context]['filedescription']
                with open('./uploads/' + filename, 'r') as file:
                        output += description + ' ' + file.read() + ' '
            elif context in global_drafts:
                if global_drafts[context]['answer_draft_input'] != "":
                    output += global_drafts[context]['answer_draft_input'] + ' '
                if len(global_drafts[context]['files']) != 0:
                    # TODO: handle multiple files
                    for i in range(len(global_drafts[context]['files'])):
                        filename = global_drafts[context]['files'][i]['filename']
                        description = global_drafts[context]['files'][i]['filedescription']
                        with open('./uploads/' + filename, 'r') as file:
                            output += description + ' ' + file.read() + ' '
                # filename = drafts[context]['files'][0]['filename']
                # description = drafts[context]['files'][0]['filedescription']
                # with open('./uploads/' + filename, 'r') as file:
                #     output += description + ' ' + file.read() + ' '
            # filename = uploaded_files[context]['filename']
            # description = uploaded_files[context]['filedescription']
            # with open('./uploads/' + filename, 'r') as file:
            #     output += description + ' ' + file.read() + ' '
        # elif context in drafts:
        #     output += drafts[context] + ' '

    return output


def get_and_update_uploaded_files(file_id, filename, filedescription):
    # upload files
    if os.path.exists('database/uploaded_files.json'):
        with open('database/uploaded_files.json', 'r') as file:
            uploaded_files = json.load(file)
    else:
        uploaded_files = {}

    uploaded_files[file_id] = {'filename': filename, 
                                'filedescription': filedescription}
    
    with open('database/uploaded_files.json', 'w') as file:
        json.dump(uploaded_files, file, indent=4)

    return uploaded_files


def get_and_update_global_drafts(draft_name, answer_draft_input, file_id, filename, filedescription, message):
    print("draft_name", draft_name)
    print("answer_draft_input", answer_draft_input)
    print("file_id", file_id)
    print("filename", filename)
    print("filedescription", filedescription)

    ### store draft_inputs: draft_name -> draft_input
    if os.path.exists('database/draft_inputs.json'):
        with open('database/draft_inputs.json', 'r') as file:
            drafts_inputs = json.load(file)
    else:
        drafts_inputs = {}
    
    drafts_inputs[draft_name] = re.sub(r'\s*\n+', '\n', answer_draft_input)

    with open('database/draft_inputs.json', 'w') as file:
        json.dump(drafts_inputs, file, indent=4)

    
    ### store global drafts
    if os.path.exists('database/global_drafts.json'):
        with open('database/global_drafts.json', 'r') as file:
            global_drafts = json.load(file)
    else:
        global_drafts = {}

    
    if filename == '':
        global_drafts[draft_name] = {
            "answer_draft_input": answer_draft_input,
            "files": []
        }
        
    else:
        global_drafts[draft_name] = {
            "answer_draft_input": answer_draft_input,
            "files": [  # TODO: handle multiple files
                {
                    'file_id': file_id,
                    'filename': filename, 
                    'filedescription': filedescription
                }
            ]
        }
        message["files"] = "file upload successful"
    
    with open('database/global_drafts.json', 'w') as file:
        json.dump(global_drafts, file, indent=4)

    if answer_draft_input != '':
        message["answer_draft"] = "draft submission successful"

    return global_drafts, drafts_inputs, message 


def parse_context_curation(answer):
    print("In parse_contxt")
    print("Answer from GPT: ", answer)
    context = {}
    # ensure each line is separated by a new line
    answer = re.sub(r'\s*\n+', '\n', answer)

    lines = answer.split("\n")
    for line in lines:
        print("Line: ", line)
        if line and '->' in line:
            title, description = line.split("->")
            # remove the number and the dot from the title
            title = title.split(".")[1].strip()
            description = description.strip()
            context[title] = description

    return context

def parse_context_elicitation(answer):
    print("In parse_contxt")
    print("Answer from GPT: ", answer)
    context = []
    # ensure each line is separated by a new line
    answer = re.sub(r'\s*\n+', '\n', answer)

    lines = answer.split("\n")
    for line in lines:
        print("Line: ", line)
        if line and ':' in line and '->' in line:
            question, sub_texts = line.split(":")
            # remove the number and the dot from the title
            question = question.split(".")[1].strip()
            description, name = sub_texts.split("->")
            description = description.strip()
            name = name.strip()
            context.append({
                "name": name,
                "description": description,
                "question": question
            })

    return context

def parse_context_root(answer):
    print("In parse_contxt_root ...")
    print("Answer from GPT: ", answer)
    context = []
    # ensure each line is separated by a new line
    answer = re.sub(r'\s*\n+', '\n', answer)

    lines = answer.split("\n")
    for line in lines:
        if line and '->' in line:
            elements = line.split("->")  # list of three elements
            reason_el = elements[0].split(':')[1].strip()
            question_el = elements[1].split(':')[1].strip()
            type_el = elements[2].split(':')[1].strip()
            name_el = elements[3].split(':')[1].strip()
            
            context.append({
                "name": name_el,
                "description": reason_el,
                "type": type_el,
                "question": question_el
            })
            # context[name_el] = {
            #     "description": reason_el,
            #     "type": type_el,
            #     "question": question_el
            # }

    return context