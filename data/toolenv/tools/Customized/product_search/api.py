import json
import re

import pandas as pd


class ProductAPI:
    def __init__(self, file_path):
        self.df = pd.read_csv(file_path)

    def extract_sku_details(self, tier_variation_str):
        try:
            # 初始化结果字典
            sku_details = {}
            # 将字符串分割成单独的变量描述
            variable_descriptions = tier_variation_str.strip("[]").split("}, {")

            for description in variable_descriptions:
                # 清理描述字符串并分割键值对
                cleaned_description = description.replace("{", "").replace("}", "")

                # 分割键值对时考虑到列表内部的逗号
                key_value_pairs = []
                buffer = ""
                in_list = False
                for char in cleaned_description:
                    if char == "[":
                        in_list = True
                    elif char == "]":
                        in_list = False
                    if char == "," and not in_list:
                        key_value_pairs.append(buffer)
                        buffer = ""
                    else:
                        buffer += char
                key_value_pairs.append(buffer)  # 添加最后一个键值对

                temp_dict = {}
                for pair in key_value_pairs:
                    if "=" in pair:
                        key, value = pair.split("=", 1)
                        key = key.strip()

                        # 特别处理带有列表的值
                        if value.startswith("[") and value.endswith("]"):
                            # 分割列表元素，移除列表元素中的额外空格
                            value = [item.strip() for item in value[1:-1].split(",")]
                        elif value.lower() == "null":
                            value = None

                        temp_dict[key] = value

                # 根据提取的值更新结果字典
                if "name" in temp_dict and "options" in temp_dict:
                    sku_details[temp_dict["name"].lower()] = temp_dict["options"]
                if "images" in temp_dict:
                    sku_details["images"] = temp_dict["images"]
            return sku_details
        except Exception as e:
            return str(e)  # 如果解析失败，返回错误信息

    def process_image_link(self, image_hash):
        if not image_hash:
            return "No image available."
        else:
            return f"https://cf.shopee.sg/file/{image_hash}/"

    def process_link(self, shop_id, item_id):
        return f"https://shopee.co.id/product/{shop_id}/{item_id}/"

    def clean_description(self, description):
        """清洁和处理商品描述文本"""
        # 去除额外的空白字符和转义字符
        cleaned_description = re.sub(r"\s+", " ", description).strip()
        return cleaned_description

    def parse_global_attribute_details(self, attribute_details_str):
        """Parse the global_attribute_details field into a simplified dictionary."""
        parsed_details = {}

        try:
            # Adjusting the regular expression to correctly capture the actual value
            # Focusing on capturing the 'value' after the 'value=' and before the next attribute starts
            attributes = re.findall(
                r"name=([^,]+),[^}]*?value=([^,}]+)", attribute_details_str
            )

            for attr in attributes:
                name, value = attr
                name = name.strip()
                value = value.strip()

                # Handle multiple values for the same attribute name
                if name in parsed_details:
                    if isinstance(parsed_details[name], list):
                        parsed_details[name].append(value)
                    else:
                        parsed_details[name] = [parsed_details[name], value]
                else:
                    parsed_details[name] = value

            # Ensuring that the values are unique and in a list if there are multiple values
            for key, val in parsed_details.items():
                if isinstance(val, list):
                    parsed_details[key] = list(set(val))

            return parsed_details
        except Exception as e:
            return {"error": str(e)}

    def get_product_details(self, item_id):
        item_id = int(item_id)
        """Get detailed information for a specified product."""
        try:
            product = self.df[self.df["item_id"].eq(item_id)].iloc[0]
        except IndexError:
            return {"error": "Item not found"}

        # Construct a details dictionary including all fields from the CSV
        details = {column: product[column] for column in self.df.columns}

        # Process specific fields
        details["description"] = self.clean_description(product["description"])
        sku_details = self.extract_sku_details(product["tier_variation"])

        details["size"] = sku_details.get("sizes", [])
        details["colors"] = sku_details.get("colors", [])
        image_hash = (
            sku_details["images"][0]
            if "images" in sku_details and sku_details["images"]
            else ""
        )
        details["image"] = self.process_image_link(image_hash)
        details["global_attribute_details"] = self.parse_global_attribute_details(
            product["global_attribute_details"]
        )

        details["url"] = self.process_link(product["shop_id"], product["item_id"])
        details.pop("is_rich_text")
        details.pop("tier_variation")
        return details

    def search_products(self, category, color=None, size=None, priceRange=None):
        # 根据类别进行筛选
        category_conditions = (
            (self.df["level1_global_be_category"].str.lower() == category.lower())
            | (self.df["level2_global_be_category"].str.lower() == category.lower())
            | (self.df["level3_global_be_category"].str.lower() == category.lower())
        )
        results = self.df[category_conditions]

        # 过滤颜色和尺寸
        if color or size:
            filtered_results = []
            for _, row in results.iterrows():
                sku_details = self.extract_sku_details(row["tier_variation"])
                # 检查颜色和尺寸是否在列表中，如果这些属性存在
                if (
                    color
                    and ("colors" in sku_details)
                    and (color not in sku_details["colors"])
                ):
                    continue
                if (
                    size
                    and ("sizes" in sku_details)
                    and (size not in sku_details["sizes"])
                ):
                    continue
                if row["stock"] == 0:
                    continue
                filtered_results.append(row)
                # 限制结果数量为5个
                if len(filtered_results) >= 5:
                    break
            results = pd.DataFrame(filtered_results)

        # 过滤价格范围
        if priceRange and not results.empty:
            min_price = priceRange.get("min", 0)
            max_price = priceRange.get("max", float("inf"))
            results = results[
                (results["price"] >= min_price) & (results["price"] <= max_price)
            ]

        # 确保结果不超过5个
        if len(results) > 5:
            results = results.head(5)

        # 在此处添加对 'url' 和 'image' 的处理
        for idx, row in results.iterrows():
            sku_details = self.extract_sku_details(row["tier_variation"])
            image_hash = (
                sku_details["images"][0]
                if "images" in sku_details and sku_details["images"]
                else ""
            )
            results.at[idx, "image"] = self.process_image_link(image_hash)
            results.at[idx, "url"] = self.process_link(row["shop_id"], row["item_id"])

        # 处理空结果的情况
        if results.empty:
            return []

        results = results[["item_id", "name", "stock", "url", "image", "price"]]
        return results.to_dict(orient="records")

def product_search(category, color=None, size=None, priceRange=None):
    ps = ProductAPI(
        "/Users/huiyu.chen/Documents/WorkNotes/24-02-ShopGuide/Step2_Experiment/FineTuningFuctionCalling/api/item_info_shop_418901918.csv"
    )
    search_results_json = ps.search_products(
        category,
        color=color,
        size=size,
        priceRange=priceRange,
    )
    return search_results_json

# 用法示例
if __name__ == "__main__":
    ps = ProductAPI(
        "/Users/huiyu.chen/Documents/WorkNotes/24-02-ShopGuide/Step2_Experiment/FineTuningFuctionCalling/api/item_info_shop_418901918.csv"
    )
    # search_results_json = ps.search_products(
    #     "Skirts",
    #     # color="Black",
    #     size=None,
    #     priceRange={"min": 100000, "max": 200000},
    # )
    # print(search_results_json)
    search_param = {"item_id": "23649650636"}

    print(ps.get_product_details(search_param))
