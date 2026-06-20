from flask import Flask, render_template, request

from analyzer import analyze_stock
from import_history import import_history
from fetch_stock import fetch_all_stocks

app = Flask(__name__)

stock_cache = None


def get_value(stock, keys):
    for key in keys:
        value = stock.get(key)

        if value is not None:
            text = str(value).strip()

            if text != "":
                return text

    return ""


def get_stock_code(stock):
    return get_value(
        stock,
        [
            "Code",
            "code",
            "股票代號",
            "證券代號",
        ],
    )


def get_stock_name(stock):
    return get_value(
        stock,
        [
            "Name",
            "name",
            "NameOfStock",
            "股票名稱",
            "證券名稱",
            "名稱",
        ],
    )


def load_stock_list(force_reload=False):
    global stock_cache

    if stock_cache is not None and not force_reload:
        return stock_cache

    raw_stocks = fetch_all_stocks()
    stock_list = []

    for stock in raw_stocks:
        code = get_stock_code(stock)
        name = get_stock_name(stock)

        if code != "" and name != "":
            stock_list.append(
                {
                    "code": code,
                    "name": name,
                }
            )

    stock_cache = stock_list

    return stock_list


def find_stock_by_keyword(keyword):
    keyword = keyword.strip()

    if keyword == "":
        return None

    stock_list = load_stock_list()

    for stock in stock_list:
        if stock["code"] == keyword:
            return stock

    for stock in stock_list:
        if stock["name"] == keyword:
            return stock

    for stock in stock_list:
        if keyword.lower() in stock["name"].lower():
            return stock

    return None


def load_real_analysis(stock):
    stock_code = stock["code"]
    stock_name = stock["name"]

    result = analyze_stock(stock_code)

    if result.get("success"):
        return result

    import_history(
        stock_code=stock_code,
        stock_name=stock_name,
        month_count=6,
    )

    result = analyze_stock(stock_code)

    return result


@app.route("/")
def index():
    try:
        stock_list = load_stock_list()

        return render_template(
            "index.html",
            stock_list=stock_list,
            error_message="",
        )

    except Exception as error:
        return render_template(
            "index.html",
            stock_list=[],
            error_message=f"Failed to load TWSE stock list: {error}",
        )


@app.route("/analyze", methods=["POST"])
def analyze():
    keyword = request.form.get("keyword", "").strip()

    if keyword == "":
        result = {
            "success": False,
            "message": "Please enter a stock code or stock name.",
        }

        return render_template("result.html", result=result)

    try:
        stock = find_stock_by_keyword(keyword)

        if stock is None:
            result = {
                "success": False,
                "message": f"Stock not found from TWSE stock list: {keyword}",
            }

            return render_template("result.html", result=result)

        result = load_real_analysis(stock)

    except Exception as error:
        result = {
            "success": False,
            "message": f"Analysis failed: {error}",
        }

    return render_template("result.html", result=result)


@app.route("/reload-stocks")
def reload_stocks():
    try:
        stock_list = load_stock_list(force_reload=True)

        return render_template(
            "index.html",
            stock_list=stock_list,
            error_message="TWSE stock list reloaded successfully.",
        )

    except Exception as error:
        return render_template(
            "index.html",
            stock_list=[],
            error_message=f"Failed to reload TWSE stock list: {error}",
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8088, debug=True)