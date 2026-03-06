from google.genai import types
from gemini import llm_client, MODEL, extract_text
from tools import FUNCTIONS, CONFIRM_REQUIRED, make_gemini_config

config = make_gemini_config()

SYSTEM_CONTENTS = [
    types.Content(role="user", parts=[types.Part(text="You are my trading assistant. Help me trade on DhanHQ.")]),
    types.Content(role="model", parts=[types.Part(text="I'm your DhanHQ trading assistant. I can help you place orders (market/limit), check holdings, positions, fund balance, search for stocks, and answer market research questions with live data. What would you like to do?")]),
]


def format_confirmation(func_name, args):
    """Format a human-readable confirmation message for trade actions."""
    if func_name == "place_market_order":
        return (
            f"\n  >> {args.get('transaction_type', 'BUY')} {args.get('quantity')} shares of "
            f"{args.get('stock_name')} at MARKET price "
            f"(product: {args.get('product_type', 'CNC')})"
            f"\n  Confirm? (y/n): "
        )
    elif func_name == "place_limit_order":
        return (
            f"\n  >> {args.get('transaction_type', 'BUY')} {args.get('quantity')} shares of "
            f"{args.get('stock_name')} at LIMIT price Rs.{args.get('price')} "
            f"(product: {args.get('product_type', 'CNC')})"
            f"\n  Confirm? (y/n): "
        )
    elif func_name == "cancel_order":
        return f"\n  >> Cancel order {args.get('order_id')}\n  Confirm? (y/n): "
    return f"\n  >> Execute {func_name}({args})\n  Confirm? (y/n): "


def process_function_calls(response, contents):
    """Process function calls from Gemini response, handling confirmation for trade actions."""
    from tools import execute_function
    while response.candidates and response.candidates[0].content.parts:
        function_calls = [p for p in response.candidates[0].content.parts if p.function_call]
        if not function_calls:
            break

        contents.append(response.candidates[0].content)
        function_response_parts = []

        for part in function_calls:
            fc = part.function_call
            func_name = fc.name
            args = dict(fc.args)

            if func_name in CONFIRM_REQUIRED:
                confirm = input(format_confirmation(func_name, args))
                if confirm.lower() != "y":
                    function_response_parts.append(
                        types.Part.from_function_response(name=func_name, response={"status": "cancelled", "message": "User declined the action"})
                    )
                    continue

            result = execute_function(func_name, args)
            function_response_parts.append(
                types.Part.from_function_response(name=func_name, response=result)
            )

        contents.append(types.Content(role="user", parts=function_response_parts))
        response = llm_client.models.generate_content(model=MODEL, contents=contents, config=config)

    return response


def main():
    contents = list(SYSTEM_CONTENTS)

    print("=" * 50)
    print("  DhanHQ Trading Assistant")
    print(f"  Powered by Gemini ({MODEL})")
    print("  Type 'quit' or 'exit' to stop")
    print("=" * 50)
    print()

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            print("Goodbye!")
            break

        contents.append(types.Content(role="user", parts=[types.Part(text=user_input)]))

        try:
            response = llm_client.models.generate_content(model=MODEL, contents=contents, config=config)
            response = process_function_calls(response, contents)

            if response.candidates and response.candidates[0].content.parts:
                contents.append(response.candidates[0].content)
                text = extract_text(response)
                if text:
                    print(f"\nAssistant: {text}\n")
            else:
                print("\nAssistant: (no response)\n")

        except Exception as e:
            print(f"\nError: {e}\n")
            contents.pop()


if __name__ == "__main__":
    main()
