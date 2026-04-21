import os
from dotenv import load_dotenv
import glob
import json
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, FileSearchTool, Tool , FunctionTool, MCPTool
from openai.types.responses.response_input_param import FunctionCallOutput, ResponseInputItemParam

load_dotenv()


project_client=AIProjectClient(
    endpoint=os.getenv("PROJECT_ENDPOINT"),
    credential=DefaultAzureCredential(),
)
openai_client=project_client.get_openai_client()


# vector_store_id = "vs_Jcil4ltilKmpVOtRb4LOj4SY"
# vector_store_id = "vs_b7rlbhijymaYbQyj7e5sUgW9"
vector_store_id=""
if vector_store_id:
    vector_store=openai_client.vector_stores.retrieve(vector_store_id)
    print(f"Using existing vector store with id: {vector_store.id} and name: {vector_store.name}")
else:
    vector_store=openai_client.vector_stores.create(
        name="ContosoPizzaStores",
    )
    print(f"Created vector store with id: {vector_store.id} and name: {vector_store.name}")

    for file_path in glob.glob("documents/*.md"):
        file=openai_client.vector_stores.files.upload_and_poll(
            vector_store_id=vector_store.id,
            file=open(file_path, "rb")
        )
        print(f"Uploaded file with id: {file.id} to vector store")

mcpTool= MCPTool(
    server_label="contoso-pizza-mcp",
    server_url="https://ca-pizza-mcp-sc6u2typoxngc.graypond-9d6dd29c.eastus2.azurecontainerapps.io/sse",
    require_approval="never",
)


func_tool=FunctionTool(
    name="get_pizza_quantity",
    parameters={
        "type":"object",
        "properties":{
            "people":{
                "type":"integer",
                "description":"Number of people to order pizza for",
            },
        },
        "required":["people"],
        "additionalProperties":False,
    },
    description="Get the quantity of pizza to order based on the number of people.",
    strict=True,
)


def get_pizza_quantity(people:int)->int:
    print(f"[FUNCTION CALL: get_pizza_quantity] calculating pizza quantity for {people} people.")
    return f"For {people} you need to order {people//2+people%2} pizzas."
    # return json.dumps({"pizza_quantity": people//2+people%2})


toolset:list[Tool]=[]
toolset.append(
    FileSearchTool(
        vector_store_ids=[vector_store.id],
    )
)
toolset.append(func_tool)
# toolset.append(mcpTool)


agent=project_client.agents.create_version(
    agent_name="pizza-agent",
    definition=PromptAgentDefinition(
        model=os.environ["MODEL_DEPLOYMENT_NAME"],
        instructions=open("instructions.txt").read(),
        # instructions="You are a helpful support assistant for Microsoft Foundry. Always provide concise, step-by-step answers."
        tools=toolset,
    ),
    
)
print(f"Created agent with id: {agent.id} and model: {agent.definition.model} , Agent Version: {agent.version}"),


conversation = openai_client.conversations.create()
print(f"Started conversation with id: {conversation.id}")

while True:
    user_input = input("You: ")
    if user_input.lower() == "exit":
        print("Exiting conversation.")
        break

    response=openai_client.responses.create(
        model="gpt-4o-mini",
        conversation=conversation.id,
        input=user_input,
        extra_body={
            "agent_reference":{
                "name": agent.name,
                "type":"agent_reference"
            }
        },
        # agent_reference={
        #     "name": agent.name
        # }
    )

    input_list:list[ResponseInputItemParam]=[]
    for item in response.output:
        if item.type=="function_call":
            if item.name =="get_pizza_quantity":
                pizza_quantity=get_pizza_quantity(**json.loads(item.arguments))
                print(f"Pizza quantity: {pizza_quantity}")
                # input_list.append({
                #     # FunctionCallOutput(
                #     #     type="function_call_output",
                #     #     name=item.name,
                #     #     call_id= item.call_id,
                #     #     # content=json.dumps({"pizza_quantity":pizza_quantity}),
                #     #     content=str(pizza_quantity),
                #     # )
                #     "tool_call_id":item.call_id,
                #     "role":"tool",
                #     "name":"get_pizza_quantity",
                #     "content":pizza_quantity,
                # }
                # )
                input_list.append(
                    FunctionCallOutput(
                        type="function_call_output",
                        # name=item.name,
                        call_id= item.call_id,
                        # content=str(pizza_quantity),
                        output=json.dumps({
                            "result": pizza_quantity
                        }),
                    )
                )
    if input_list:
        print(f"input list: {input_list}")
        response=openai_client.responses.create(
            previous_response_id=response.id,
            input=input_list,
            model="gpt-4o-mini",
            extra_body={
                "agent_reference": {
                    "name": agent.name,
                    "type": "agent_reference"
                }
            },
            

        )

    print(f"assistant: {response.output_text}")